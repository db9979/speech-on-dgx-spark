import SwiftUI

/// Kalender und E-Mail in der App (plan kalender-mail Stufe 4, Dominik 2026-10-19 „baue alle Stufen“): the same
/// pages as in the panel, with this iPhone's key (iphone.THINGS "calendar", "mail", "mailmanage", "mailsend" on the
/// Spark: each opens only with its own function released for the profile). Every rule stays on the Spark: which
/// appointment may change, where a new one may go, what a mail may be moved to, what goes out.
///
/// Kept on the iPhone (Merken.swift, 1b): the appointments of four weeks, the newest 50 mails of the inbox and up to
/// 20 opened mails with their text; deleted when the function goes off, on unpairing and for another profile.
/// Texts from mail are other people's words: shown as plain text only, never a link or a picture that opens.

// ---------------------------------------------------------------- the data
struct CalEvent: Identifiable, Hashable {
    let start: Date
    let end: Date
    let allday: Bool
    let title: String
    let location: String
    let cal: Int
    let edit: Bool
    var id: String { "\(cal)|\(Int(start.timeIntervalSince1970))|\(title)" }
}

struct CalView {
    var connected = true
    var calendars: [String] = []
    var add: [Int] = []
    var events: [CalEvent] = []
    var errors: [String] = []
    var notes: [String] = []      // changes the calendar refused (the Spark's copy went back; Stufe 2)
}

struct MailItem: Identifiable, Hashable {
    let id: String
    let from: String
    let subject: String
    let date: Date
    var unread: Bool
    let box: Int
    var flagged = false
    var attach = false
}

/// A folder of one mailbox (Mailclient Stufe A, postfach.tree): read like the inbox; own folders can be renamed
/// or, when empty, removed (the Spark checks; folders of the mail program and of „Mails aufräumen“ never).
struct MailFolder: Identifiable, Hashable {
    let account: String
    let name: String
    let title: String
    let role: String
    let depth: Int
    let unseen: Int
    let own: Bool
    var id: String { account + "|" + name }
    /// messages are moved only out of the inbox, an own folder or the archive (postfach._source)
    var movable: Bool { role == "inbox" || role == "folder" || role == "archive" }
}

struct MailText {
    let id: String
    let from: String
    let to: String
    let subject: String
    let date: Date
    let text: String
    let files: [String]
    /// the attachments to fetch (Anhang laden, with Mails ordnen): number, name, size in KB
    var parts: [(n: Int, name: String, kb: Int)] = []
}

extension SparkAPI {
    /// "<account>:<uid>" as the Spark gives it
    static func isMail(_ id: String) -> Bool { id.range(of: #"^m[0-9a-f]{8}:[0-9]{1,10}$"#, options: .regularExpression) != nil }

    static func calView(_ d: [String: Any]) -> CalView {
        var v = CalView()
        v.connected = d["connected"] as? Bool ?? true
        v.calendars = (d["calendars"] as? [String] ?? []).map { String($0.prefix(80)) }
        v.add = d["add"] as? [Int] ?? []
        v.errors = d["errors"] as? [String] ?? []
        v.notes = (d["notes"] as? [String] ?? []).prefix(10).map { String($0.prefix(80)) }
        v.events = (d["events"] as? [[String: Any]] ?? []).prefix(500).compactMap { e in
            guard let s = (e["start"] as? NSNumber)?.doubleValue, let en = (e["end"] as? NSNumber)?.doubleValue else { return nil }
            return CalEvent(start: Date(timeIntervalSince1970: s), end: Date(timeIntervalSince1970: en),
                            allday: e["allday"] as? Bool ?? false, title: String((e["title"] as? String ?? "").prefix(200)),
                            location: String((e["location"] as? String ?? "").prefix(200)), cal: e["cal"] as? Int ?? 0,
                            edit: e["edit"] as? Bool ?? false)
        }
        return v
    }

    static var zone: String { TimeZone.current.identifier }

    func calendarView(from day: Date, days: Int) async throws -> [String: Any] {
        try await object("GET", "api/profile/calendar/view",
                         query: ["start": Self.isoDay(day), "days": String(days), "tz": Self.zone])
    }

    static func isoDay(_ d: Date) -> String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }

    static func isoMinute(_ d: Date) -> String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return f.string(from: d)
    }

    /// the form's fields as the Spark's page form takes them (calendars.page_item)
    static func calFields(title: String, allday: Bool, start: Date, end: Date, location: String) -> [String: Any] {
        let endDay = Calendar.current.date(byAdding: .day, value: 1, to: end) ?? end   // all day: the end is the next day
        return ["title": String(title.prefix(200)), "allday": allday, "location": String(location.prefix(200)),
                "start": allday ? isoDay(start) : isoMinute(start), "end": allday ? isoDay(endDay) : isoMinute(end)]
    }

    /// Schnell eintragen: one line as the form's fields (calendars.quick on the Spark, fixed rules, nothing saved)
    func quickEvent(_ text: String) async throws -> [String: Any] {
        try await object("GET", "api/profile/calendar/quick", query: ["text": String(text.prefix(200)), "tz": Self.zone])
    }

    /// the fields of an appointment as shown, moved by `days` (+1 Tag, +1 Woche; 0 = as it is, for „Rückgängig“)
    static func moved(_ e: CalEvent, days: Int) -> [String: Any] {
        let c = Calendar.current
        let s = c.date(byAdding: .day, value: days, to: e.start) ?? e.start
        let en = c.date(byAdding: .day, value: days, to: e.end) ?? e.end
        return calFields(title: e.title, allday: e.allday, start: s,
                         end: e.allday ? (c.date(byAdding: .day, value: -1, to: en) ?? s) : en, location: e.location)
    }

    func addEvent(_ fields: [String: Any], calendar: String) async throws {
        var b = fields
        b["calendar"] = calendar
        b["tz"] = Self.zone
        _ = try await call("POST", "api/profile/calendar/event", body: b)
    }

    /// change (new fields) or delete (nil) exactly the appointment shown; 409 when it is no longer there like this
    func changeEvent(_ e: CalEvent, _ new: [String: Any]?) async throws {
        var b: [String: Any] = ["change": new == nil ? "delete" : "edit", "cal": e.cal, "title": e.title,
                                "start": Int(e.start.timeIntervalSince1970), "tz": Self.zone]
        if let new { b["new"] = new }
        _ = try await call("PUT", "api/profile/calendar/event", body: b)
    }

    static func inbox(_ d: [String: Any]) -> (items: [MailItem], boxes: [String], connected: Bool, errors: [String]) {
        let items = (d["items"] as? [[String: Any]] ?? []).prefix(50).compactMap { x -> MailItem? in
            guard let id = x["id"] as? String, isMail(id) else { return nil }
            return MailItem(id: id, from: String((x["from"] as? String ?? "").prefix(150)),
                            subject: String((x["subject"] as? String ?? "").prefix(200)),
                            date: Date(timeIntervalSince1970: (x["date"] as? NSNumber)?.doubleValue ?? 0),
                            unread: x["unread"] as? Bool ?? false, box: x["box"] as? Int ?? 0,
                            flagged: x["flagged"] as? Bool ?? false, attach: x["attach"] as? Bool ?? false)
        }
        return (Array(items), d["boxes"] as? [String] ?? [], d["connected"] as? Bool ?? true, d["errors"] as? [String] ?? [])
    }

    static func mailText(_ m: [String: Any]) -> MailText? {
        guard let id = m["id"] as? String, isMail(id) else { return nil }
        return MailText(id: id, from: String((m["from"] as? String ?? "").prefix(150)), to: String((m["to"] as? String ?? "").prefix(200)),
                        subject: String((m["subject"] as? String ?? "").prefix(200)),
                        date: Date(timeIntervalSince1970: (m["date"] as? NSNumber)?.doubleValue ?? 0),
                        text: String((m["text"] as? String ?? "").prefix(20000)), files: (m["files"] as? [String] ?? []).prefix(20).map { String($0) },
                        parts: (m["parts"] as? [[String: Any]] ?? []).prefix(20).compactMap { p in
                            guard let n = p["n"] as? Int, (0..<20).contains(n) else { return nil }
                            return (n, String((p["name"] as? String ?? "").prefix(120)), p["kb"] as? Int ?? 0)
                        })
    }

    /// the name of an opened mail's kept page ("mail-" and its id with the colon as a dash)
    static func keptMail(_ id: String) -> String? { isMail(id) ? "mail-" + id.replacingOccurrences(of: ":", with: "-") : nil }
}

// ---------------------------------------------------------------- Kalender
@MainActor
final class KalenderModel: ObservableObject {
    @Published var v = CalView()
    @Published var loading = true
    @Published var error: String?
    @Published var keptAt: Date?
    static let span = 28

    /// four weeks from the Monday of this week
    static var first: Date {
        let c = Calendar(identifier: .iso8601)
        return c.date(from: c.dateComponents([.yearForWeekOfYear, .weekOfYear], from: Date())) ?? Calendar.current.startOfDay(for: Date())
    }

    func load(_ on: Bool) async {
        guard on else { Merken.drop("kalender"); v = CalView(); loading = false; return }
        if loading, keptAt == nil, let k = Merken.object("kalender") {
            v = SparkAPI.calView(k.d)
            keptAt = k.at
        }
        guard let api = SparkAPI.current else { loading = false; return }
        do {
            let d = try await Merken.timed("kalender") { try await api.calendarView(from: Self.first, days: Self.span) }
            v = SparkAPI.calView(d)
            Merken.keepObject("kalender", d)
            keptAt = nil
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// the days with appointments, from today on
    var days: [(Date, [CalEvent])] {
        let today = Calendar.current.startOfDay(for: Date())
        let groups = Dictionary(grouping: v.events) { Calendar.current.startOfDay(for: $0.start) }
        return groups.filter { $0.key >= today || $0.value.contains { $0.end > Date() } }
            .sorted { $0.key < $1.key }
            .map { ($0.key, $0.value.sorted { ($0.allday ? 0 : 1, $0.start) < ($1.allday ? 0 : 1, $1.start) }) }
    }
}

struct KalenderView: View {
    @ObservedObject private var talk = Conversation.shared
    @StateObject private var m = KalenderModel()
    @State private var open: CalEvent?
    @State private var form: CalForm?

    var body: some View {
        List {
            if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
            if !m.v.add.isEmpty {
                Section("Schnell eintragen") { QuickAdd(text: "") { Task { await m.load(true) } } }
            }
            if !m.v.connected {
                Text(SparkAPI.way(String(localized: "Noch kein Kalender verbunden. Im Panel unter Kalender → Einstellungen verbindest du iCloud, Nextcloud oder einen Abo-Link.")))
                    .foregroundStyle(.secondary)
            } else if !m.loading && m.days.isEmpty {
                Text("In den nächsten vier Wochen steht nichts an.").foregroundStyle(.secondary)
            }
            ForEach(m.days, id: \.0) { day, evs in
                Section {
                    ForEach(evs) { e in
                        Button { open = e } label: { row(e) }.foregroundStyle(.primary)
                    }
                } header: {
                    Text(day, format: .dateTime.weekday(.wide).day().month(.wide))
                }
            }
            if !m.v.errors.isEmpty {
                Text("Nicht erreicht: \(m.v.errors.joined(separator: ", "))").foregroundStyle(.red)
            }
            if !m.v.notes.isEmpty {
                Text("Nicht gespeichert, der Kalender hat abgelehnt: \(m.v.notes.joined(separator: ", "))").foregroundStyle(.red)
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Kalender")
        .toolbar {
            if !m.v.add.isEmpty {
                ToolbarItem(placement: .primaryAction) {
                    Button { form = CalForm(event: nil) } label: { Image(systemName: "plus") }
                        .accessibilityLabel("Neuer Termin")
                }
            }
        }
        .refreshable { await m.load(talk.allowed.areas.contains("calendar")) }
        .task { await m.load(talk.allowed.areas.contains("calendar")) }
        .overlay { if m.loading && m.keptAt == nil { LadeZeilen(rows: 5).padding() } }
        .sheet(item: $open) { e in
            KalenderDetail(e: e, calendar: m.v.calendars.indices.contains(e.cal) ? m.v.calendars[e.cal] : "",
                           change: { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { form = CalForm(event: e) } }, done: { Task { await m.load(true) } })
        }
        .sheet(item: $form) { f in
            KalenderForm(event: f.event, calendars: m.v.add.compactMap { m.v.calendars.indices.contains($0) ? m.v.calendars[$0] : nil }) {
                Task { await m.load(true) }
            }
        }
    }

    private func row(_ e: CalEvent) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 2).fill(Self.tint(e.cal)).frame(width: 4)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: e.title.isEmpty ? String(localized: "(ohne Titel)") : e.title).lineLimit(2)
                HStack(spacing: 4) {
                    if e.allday { Text("ganztägig") } else {
                        Text(e.start, format: .dateTime.hour().minute())
                        Text(verbatim: "–")
                        Text(e.end, format: .dateTime.hour().minute())
                    }
                    if !e.location.isEmpty { Text(verbatim: "· " + e.location).lineLimit(1) }
                }
                .font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    static func tint(_ i: Int) -> Color { [Color.blue, .orange, .green, .purple, .pink, .teal][abs(i) % 6] }
}

struct CalForm: Identifiable {
    let event: CalEvent?
    var id: String { event?.id ?? "neu" }
}

/// Schnell eintragen (Dominik 2026-10-19 „2a“, as on the page Kalender): one line; the Spark reads it with fixed
/// rules and shows what it understood, only „Eintragen“ saves (into the first own calendar, like the page).
struct QuickAdd: View {
    @State var text: String
    let saved: () -> Void
    @State private var fields: [String: Any]?
    @State private var busy = false
    @State private var done = false
    @State private var error: String?

    var body: some View {
        TextField("Morgen 15 Uhr Zahnarzt", text: $text)
            .submitLabel(.done)
            .onSubmit { Task { await read() } }
            .onChange(of: text) { _, _ in fields = nil; done = false }
            .task { if !text.isEmpty { await read() } }
        if let f = fields {
            VStack(alignment: .leading, spacing: 4) {
                Text(verbatim: f["title"] as? String ?? "").font(.headline)
                Text(verbatim: Self.when(f)).font(.subheadline).foregroundStyle(.secondary)
                if let l = f["location"] as? String, !l.isEmpty { Text(verbatim: l).font(.subheadline).foregroundStyle(.secondary) }
            }
            Button("Eintragen") { Task { await save(f) } }.disabled(busy)
        }
        if done { Text("Eingetragen.").foregroundStyle(.secondary) }
        if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
    }

    /// the start (and end) the Spark understood, in this iPhone's words
    static func when(_ f: [String: Any]) -> String {
        let iso = DateFormatter()
        iso.locale = Locale(identifier: "en_US_POSIX")
        let all = f["allday"] as? Bool ?? false
        iso.dateFormat = all ? "yyyy-MM-dd" : "yyyy-MM-dd'T'HH:mm"
        guard let s = iso.date(from: f["start"] as? String ?? "") else { return "" }
        if all { return s.formatted(.dateTime.weekday(.wide).day().month(.wide)) }
        let e = iso.date(from: f["end"] as? String ?? "") ?? s
        return s.formatted(.dateTime.weekday(.wide).day().month(.wide).hour().minute()) + " – " + e.formatted(.dateTime.hour().minute())
    }

    private func read() async {
        guard let api = SparkAPI.current, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        do {
            fields = try await api.quickEvent(text)
            error = nil
        } catch {
            fields = nil
            self.error = error.localizedDescription
        }
    }

    private func save(_ f: [String: Any]) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        var b = f
        b.removeValue(forKey: "found")
        do {
            try await api.addEvent(b, calendar: "")
            fields = nil
            text = ""
            done = true
            saved()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct KalenderDetail: View {
    @Environment(\.dismiss) private var dismiss
    let calendar: String
    let change: () -> Void
    let done: () -> Void
    @State private var e: CalEvent
    @State private var before: CalEvent?      // after +1 Tag/+1 Woche: the appointment as it was, for „Rückgängig“
    @State private var asking = false
    @State private var busy = false
    @State private var error: String?

    init(e: CalEvent, calendar: String, change: @escaping () -> Void, done: @escaping () -> Void) {
        _e = State(initialValue: e)
        self.calendar = calendar
        self.change = change
        self.done = done
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(verbatim: e.title).font(.headline)
                    if e.allday {
                        Text(e.start, format: .dateTime.weekday(.wide).day().month(.wide))
                    } else {
                        Text(e.start, format: .dateTime.weekday(.wide).day().month(.wide).hour().minute())
                        Text(e.end, format: .dateTime.hour().minute())
                    }
                    if !e.location.isEmpty { LabeledContent("Ort") { Text(verbatim: e.location) } }
                    if !calendar.isEmpty { LabeledContent("Kalender") { Text(verbatim: calendar) } }
                }
                if e.edit {
                    Section {
                        Button("Ändern") { dismiss(); change() }
                        HStack {
                            Button("+1 Tag") { Task { await move(1) } }.buttonStyle(.bordered)
                            Button("+1 Woche") { Task { await move(7) } }.buttonStyle(.bordered)
                        }
                        .disabled(busy)
                        if before != nil {
                            Button("Rückgängig") { Task { await undo() } }.disabled(busy)
                        }
                        Button("Löschen", role: .destructive) { asking = true }.disabled(busy)
                    }
                } else {
                    Section { Text("Diesen Termin änderst du im Kalender, aus dem er kommt (wiederholt oder geteilt).").foregroundStyle(.secondary) }
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle("Termin")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .confirmationDialog("Termin löschen?", isPresented: $asking, titleVisibility: .visible) {
                Button("Löschen", role: .destructive) { Task { await delete() } }
            }
        }
    }

    /// +1 Tag, +1 Woche (Dominik 2026-10-19 „1a“): the Spark changes exactly this appointment; „Rückgängig“ moves it back
    private func move(_ days: Int) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        let c = Calendar.current
        do {
            try await api.changeEvent(e, SparkAPI.moved(e, days: days))
            before = e
            e = CalEvent(start: c.date(byAdding: .day, value: days, to: e.start) ?? e.start,
                         end: c.date(byAdding: .day, value: days, to: e.end) ?? e.end, allday: e.allday, title: e.title,
                         location: e.location, cal: e.cal, edit: e.edit)
            error = nil
            done()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func undo() async {
        guard let api = SparkAPI.current, let b = before else { return }
        busy = true
        defer { busy = false }
        do {
            try await api.changeEvent(e, SparkAPI.moved(b, days: 0))
            e = b
            before = nil
            error = nil
            done()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func delete() async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            try await api.changeEvent(e, nil)
            done()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct KalenderForm: View {
    @Environment(\.dismiss) private var dismiss
    let event: CalEvent?
    let calendars: [String]
    let saved: () -> Void
    @State private var title = ""
    @State private var allday = false
    @State private var start = Date()
    @State private var end = Date().addingTimeInterval(3600)
    @State private var location = ""
    @State private var calendar = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Titel", text: $title)
                    Toggle("Ganztägig", isOn: $allday)
                    DatePicker("Beginn", selection: $start, displayedComponents: allday ? [.date] : [.date, .hourAndMinute])
                    DatePicker("Ende", selection: $end, in: start..., displayedComponents: allday ? [.date] : [.date, .hourAndMinute])
                    TextField("Ort", text: $location)
                }
                if event == nil && calendars.count > 1 {
                    Picker("Kalender", selection: $calendar) {
                        ForEach(calendars, id: \.self) { Text(verbatim: $0).tag($0) }
                    }
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle(event == nil ? Text("Neuer Termin") : Text("Termin ändern"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Speichern") { Task { await save() } }
                        .disabled(busy || title.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .onAppear {
                if let e = event {
                    title = e.title; allday = e.allday; start = e.start; location = e.location
                    end = e.allday ? (Calendar.current.date(byAdding: .day, value: -1, to: e.end) ?? e.start) : e.end
                } else {
                    calendar = calendars.first ?? ""
                    let c = Calendar.current
                    start = c.date(bySetting: .minute, value: 0, of: Date().addingTimeInterval(3600)) ?? Date()
                    end = start.addingTimeInterval(3600)
                }
            }
            .onChange(of: start) { _, s in if end < s { end = s.addingTimeInterval(allday ? 0 : 3600) } }
        }
    }

    private func save() async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        let fields = SparkAPI.calFields(title: title, allday: allday, start: start, end: end, location: location)
        do {
            if let e = event { try await api.changeEvent(e, fields) } else { try await api.addEvent(fields, calendar: calendar) }
            saved()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// ---------------------------------------------------------------- E-Mail
@MainActor
final class PostModel: ObservableObject {
    @Published var items: [MailItem] = []
    @Published var boxes: [String] = []
    @Published var connected = true
    @Published var errors: [String] = []
    @Published var loading = true
    @Published var error: String?
    @Published var keptAt: Date?
    /// nil: the inbox of every mailbox; else one folder (Ordner, with Mails ordnen)
    @Published var folder: MailFolder?
    /// Mehrfachauswahl: the ids ticked in the list's edit mode
    @Published var picked = Set<String>()
    /// Suche (Mailclient Stufe C): words, von:, betreff:, hat:anhang, ist:markiert; the Spark compares, never runs
    @Published var query = ""

    func load(_ on: Bool) async {
        guard on else { Merken.drop("post"); Merken.dropAll("mail-"); items = []; loading = false; return }
        if let f = folder {
            guard let api = SparkAPI.current else { loading = false; return }
            do {
                show(try await api.object("GET", "api/profile/mail/folder", query: ["account": f.account, "folder": f.name, "q": String(query.prefix(100))], timeout: 60))
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
            loading = false
            return
        }
        if !query.isEmpty {     // a search is never kept on the iPhone
            guard let api = SparkAPI.current else { loading = false; return }
            do {
                show(try await api.object("GET", "api/profile/mail/inbox", query: ["q": String(query.prefix(100))], timeout: 60))
                error = nil
            } catch {
                self.error = error.localizedDescription
            }
            loading = false
            return
        }
        if loading, keptAt == nil, let k = Merken.object("post") {
            show(k.d)
            keptAt = k.at
        }
        guard let api = SparkAPI.current else { loading = false; return }
        do {
            let d = try await Merken.timed("post") { try await api.object("GET", "api/profile/mail/inbox", timeout: 60) }
            show(d)
            // only the 50 newest: sender, subject and time (never a text here)
            var cut = d
            cut["items"] = (d["items"] as? [[String: Any]] ?? []).prefix(50).map { $0 }
            Merken.keepObject("post", cut)
            keptAt = nil
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// the list by day, newest first (Dominik 2026-10-19 „4a“, as on the page)
    var days: [(Date, [MailItem])] {
        Dictionary(grouping: items) { Calendar.current.startOfDay(for: $0.date) }
            .sorted { $0.key > $1.key }
            .map { ($0.key, $0.value.sorted { $0.date > $1.date }) }
    }

    /// swipe (Dominik 2026-10-19 „5a“): archive, read or unread; the Spark decides what may happen (postfach.py)
    func act(_ x: MailItem, _ action: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.call("POST", "api/profile/mail/act",
                                   body: ["id": x.id, "action": action, "folder": "", "mid": "", "src": folder?.name ?? "INBOX"])
            if let kept = SparkAPI.keptMail(x.id) { Merken.drop(kept) }
            error = nil
            await load(true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Mehrfachauswahl: one action on every ticked mail (at most 50; a move goes into a folder of one mailbox)
    func actMany(_ action: String, _ into: String = "") async {
        guard let api = SparkAPI.current, !picked.isEmpty else { return }
        do {
            _ = try await api.object("POST", "api/profile/mail/acts",
                                     body: ["ids": Array(picked.prefix(50)), "action": action, "folder": into, "src": folder?.name ?? "INBOX"])
            for id in picked { if let kept = SparkAPI.keptMail(id) { Merken.drop(kept) } }
            picked = []
            error = nil
            await load(true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func show(_ d: [String: Any]) {
        let r = SparkAPI.inbox(d)
        items = r.items; boxes = r.boxes; connected = r.connected; errors = r.errors
    }
}

struct PostView: View {
    @ObservedObject private var talk = Conversation.shared
    @StateObject private var m = PostModel()
    @State private var writing: MailDraft?
    @State private var picking = false
    @State private var choosing = false
    @State private var moveTo: [String] = []
    @State private var rules = false

    private var manage: Bool { talk.allowed.areas.contains("mailmanage") }
    /// the search words the Spark knows besides plain words (mail._words)
    private static let chips: [(String, LocalizedStringKey)] = [("ist:markiert", "★ Markiert"), ("hat:anhang", "📎 Mit Anhang"),
                                                                ("ist:ungelesen", "Ungelesen"), ("von:", "von: Absender"), ("betreff:", "betreff: Wort")]

    var body: some View {
        List(selection: $m.picked) {
            if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
            if !m.connected {
                Text(SparkAPI.way(String(localized: "Noch kein Postfach verbunden. Im Panel unter E-Mail → Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder IMAP.")))
                    .foregroundStyle(.secondary)
            } else if !m.loading && m.items.isEmpty {
                Text(!m.query.isEmpty ? LocalizedStringKey("Keine passende Mail.")
                     : m.folder == nil ? LocalizedStringKey("Keine Mail in den letzten 14 Tagen.") : LocalizedStringKey("Dieser Ordner ist leer."))
                    .foregroundStyle(.secondary)
            }
            ForEach(m.days, id: \.0) { day, xs in
                Section {
                    ForEach(xs) { x in
                        NavigationLink {
                            MailView(item: x, box: m.boxes.count > 1 && m.boxes.indices.contains(x.box) ? m.boxes[x.box] : "", folder: m.folder) {
                                Task { await m.load(true) }
                            }
                        } label: { row(x) }
                        .swipeActions(edge: .trailing) {
                            if manage && m.folder?.movable ?? true {
                                Button { Task { await m.act(x, "archive") } } label: { Label("Archivieren", systemImage: "archivebox") }.tint(.blue)
                            }
                            if manage {
                                Button { Task { await m.act(x, x.flagged ? "unflag" : "flag") } } label: {
                                    x.flagged ? Label("Markierung weg", systemImage: "star.slash") : Label("Markieren", systemImage: "star")
                                }
                                .tint(.yellow)
                            }
                        }
                        .swipeActions(edge: .leading) {
                            if talk.allowed.areas.contains("mailmanage") {
                                Button { Task { await m.act(x, x.unread ? "read" : "unread") } } label: {
                                    x.unread ? Label("Gelesen", systemImage: "envelope.open") : Label("Ungelesen", systemImage: "envelope.badge")
                                }
                                .tint(.orange)
                            }
                        }
                    }
                } header: {
                    Text(verbatim: Self.day(day))
                }
            }
            if !m.errors.isEmpty { Text("Nicht erreicht: \(m.errors.joined(separator: ", "))").foregroundStyle(.red) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(m.folder.map { Text(verbatim: $0.title) } ?? Text("E-Mail"))
        .environment(\.editMode, .constant(picking ? .active : .inactive))
        .toolbar {
            if manage && m.connected {
                ToolbarItem(placement: .topBarLeading) {
                    Button { choosing = true } label: { Image(systemName: "folder") }
                        .accessibilityLabel("Ordner")
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button(picking ? LocalizedStringKey("Fertig") : LocalizedStringKey("Auswählen")) { picking.toggle(); m.picked = [] }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Regeln") { rules = true }
                }
            }
            if talk.allowed.areas.contains("mailsend") && m.connected && !picking {
                ToolbarItem(placement: .primaryAction) {
                    Button { writing = MailDraft() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Neue Mail")
                }
            }
            if picking && !m.picked.isEmpty {
                ToolbarItemGroup(placement: .bottomBar) {
                    Button("Gelesen") { Task { await m.actMany("read") } }
                    Button("Markieren") { Task { await m.actMany("flag") } }
                    if m.folder?.movable ?? true { Button("Archivieren") { Task { await m.actMany("archive") } } }
                    if (m.folder?.movable ?? true) && !moveTo.isEmpty {
                        Menu("Verschieben nach …") {
                            ForEach(moveTo, id: \.self) { f in
                                Button { Task { await m.actMany("move", f) } } label: {
                                    Text(verbatim: f == "INBOX" ? String(localized: "Posteingang") : f)
                                }
                            }
                        }
                    }
                }
            }
        }
        .searchable(text: $m.query, prompt: Text("Suchen, auch von: betreff: hat:anhang"))
        .searchSuggestions {
            if m.query.isEmpty || !m.query.hasSuffix(" ") {
                ForEach(Self.chips, id: \.0) { c in Text(c.1).searchCompletion((m.query.isEmpty ? "" : m.query + " ") + c.0 + (c.0.hasSuffix(":") ? "" : " ")) }
            }
        }
        .onSubmit(of: .search) { Task { await m.load(talk.allowed.areas.contains("mail")) } }
        .onChange(of: m.query) { _, q in if q.isEmpty { Task { await m.load(talk.allowed.areas.contains("mail")) } } }
        .refreshable { await m.load(talk.allowed.areas.contains("mail")) }
        .task { await m.load(talk.allowed.areas.contains("mail")) }
        .task(id: m.picked.map { String($0.prefix(9)) }.sorted().first) { await loadMoveTo() }
        .overlay { if m.loading && m.keptAt == nil { LadeZeilen(rows: 6).padding() } }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
        .sheet(isPresented: $rules) { MailRules(start: nil) }
        .sheet(isPresented: $choosing) {
            MailFolders(current: m.folder) { f in
                choosing = false
                picking = false
                m.picked = []
                m.folder = f
                m.items = []
                m.loading = true
                Task { await m.load(true) }
            }
        }
    }

    /// the folders a move of the ticked mails may go to (one mailbox: the first ticked mail's)
    private func loadMoveTo() async {
        guard manage, let first = m.picked.first, let api = SparkAPI.current,
              let f = try? await api.object("GET", "api/profile/mail/folders", query: ["account": String(first.prefix(9))])
        else { moveTo = []; return }
        let src = m.folder?.name ?? "INBOX"
        moveTo = (m.folder == nil ? [] : ["INBOX"]) + (f["folders"] as? [String] ?? []).prefix(100).filter { $0 != src }
    }

    /// Heute, Gestern, else the date
    static func day(_ d: Date) -> String {
        let c = Calendar.current
        if c.isDateInToday(d) { return String(localized: "Heute") }
        if c.isDateInYesterday(d) { return String(localized: "Gestern") }
        return d.formatted(.dateTime.weekday(.wide).day().month(.wide))
    }

    /// two letters for the round mark: of the name, else of the address's part before the @
    static func initials(_ from: String) -> String {
        var n = name(from)
        if n.contains("@") { n = String(n.split(separator: "@").first ?? "") }
        let words = n.split(whereSeparator: { " .-_\"".contains($0) }).filter { $0.first?.isLetter == true }
        let s = words.count > 1 ? String(words[0].prefix(1)) + String(words[1].prefix(1)) : String((words.first ?? "?").prefix(2))
        return s.uppercased()
    }

    private func row(_ x: MailItem) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Circle().fill(x.unread ? Color.accentColor : .clear).frame(width: 8, height: 8).padding(.top, 14)
            Text(verbatim: Self.initials(x.from)).font(.caption.weight(.semibold)).foregroundStyle(.white)
                .frame(width: 32, height: 32).background(Circle().fill(KalenderView.tint(x.from.unicodeScalars.reduce(0) { $0 &+ Int($1.value) })))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(verbatim: Self.name(x.from)).fontWeight(x.unread ? .semibold : .regular).lineLimit(1)
                    Spacer()
                    if x.attach { Image(systemName: "paperclip").font(.caption).foregroundStyle(.secondary).accessibilityLabel("mit Anhang") }
                    if x.flagged { Image(systemName: "star.fill").font(.caption).foregroundStyle(.yellow).accessibilityLabel("markiert") }
                    Text(x.date, format: Calendar.current.isDateInToday(x.date) ? Date.FormatStyle.dateTime.hour().minute() : Date.FormatStyle.dateTime.day().month())
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text(verbatim: x.subject.isEmpty ? String(localized: "(ohne Betreff)") : x.subject)
                    .font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// the sender's name without the address
    static func name(_ from: String) -> String {
        if let r = from.range(of: #"\s*<[^>]*>$"#, options: .regularExpression), r.lowerBound > from.startIndex {
            return String(from[..<r.lowerBound])
        }
        return from
    }

    static func address(_ from: String) -> String {
        if let r = from.range(of: #"<([^>]+)>\s*$"#, options: .regularExpression) {
            return String(from[r]).trimmingCharacters(in: CharacterSet(charactersIn: "<> "))
        }
        return from.trimmingCharacters(in: .whitespaces)
    }
}

/// Ordner (Mailclient Stufe A, postfach.tree): every folder of every mailbox; tap opens one, „Neuer Ordner“ per mailbox,
/// own folders renamed or removed (only empty ones, with the code). Folder names come from the mail server: verbatim.
struct MailFolders: View {
    let current: MailFolder?
    let pick: (MailFolder?) -> Void
    @Environment(\.dismiss) private var dismiss
    struct Box: Identifiable {
        let id: String
        let name: String
        let folders: [MailFolder]
        let error: Bool
    }
    @State private var accounts: [Box] = []
    @State private var loading = true
    @State private var error: String?
    @State private var naming: (account: String, inside: String, folder: String)?
    @State private var name = ""
    @State private var removing: MailFolder?

    var body: some View {
        NavigationStack {
            List {
                Button { pick(nil) } label: {
                    Label("Alle Posteingänge", systemImage: current == nil ? "tray.full.fill" : "tray.full")
                }
                ForEach(accounts) { a in
                    Section {
                        if a.error { Text("Dieses Postfach war nicht erreichbar.").foregroundStyle(.red) }
                        ForEach(a.folders) { f in
                            Button { if f.role != "group" { pick(f) } } label: { row(f) }
                                .swipeActions(edge: .trailing) {
                                    if f.own {
                                        Button("Entfernen", role: .destructive) { removing = f }
                                        Button("Umbenennen") { name = f.title; naming = (f.account, "", f.name) }.tint(.blue)
                                    }
                                }
                                .contextMenu {
                                    if f.own || f.role == "inbox" {
                                        Button("Ordner darin anlegen") { name = ""; naming = (f.account, f.name, "") }
                                    }
                                    if f.own {
                                        Button("Umbenennen") { name = f.title; naming = (f.account, "", f.name) }
                                        Button("Entfernen", role: .destructive) { removing = f }
                                    }
                                }
                        }
                        Button("Neuer Ordner") { name = ""; naming = (a.id, "", "") }
                    } header: {
                        Text(verbatim: a.name)
                    } footer: {
                        Text("Eigene Ordner: wischen oder lange drücken zum Umbenennen oder Entfernen (nur leere). Gelöscht wird nie eine Mail.")
                    }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .overlay { if loading && accounts.isEmpty { LadeZeilen(rows: 6).padding() } }
            .navigationTitle("Ordner")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .refreshable { await load(fresh: true) }
            .task { await load(fresh: false) }
            .alert(naming?.folder.isEmpty == false ? LocalizedStringKey("Ordner umbenennen") : LocalizedStringKey("Neuer Ordner"),
                   isPresented: Binding(get: { naming != nil }, set: { if !$0 { naming = nil } })) {
                TextField("Name", text: $name)
                Button("Abbrechen", role: .cancel) { naming = nil }
                Button("Sichern") { if let n = naming { Task { await save(n) } } }
            }
            .confirmationDialog("Den leeren Ordner entfernen?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                                titleVisibility: .visible) {
                Button("Entfernen", role: .destructive) { if let f = removing { Task { await remove(f) } } }
            } message: {
                Text("Mails werden nie gelöscht: einen Ordner mit Mails lässt der Spark stehen.")
            }
        }
    }

    private func row(_ f: MailFolder) -> some View {
        HStack {
            Image(systemName: Self.icon(f.role)).foregroundStyle(f.role == "group" ? Color.secondary : Color.accentColor)
            Text(verbatim: f.title).foregroundStyle(f.role == "group" ? Color.secondary : Color.primary)
            Spacer()
            if f.unseen > 0 { Text(verbatim: "\(f.unseen)").font(.caption).foregroundStyle(.secondary) }
            if current?.id == f.id { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
        }
        .padding(.leading, CGFloat(min(f.depth, 4)) * 14)
    }

    static func icon(_ role: String) -> String {
        switch role {
        case "inbox": return "tray"
        case "sent": return "paperplane"
        case "drafts": return "doc.text"
        case "archive": return "archivebox"
        case "trash": return "trash"
        case "junk": return "xmark.bin"
        default: return "folder"
        }
    }

    private func load(fresh: Bool) async {
        guard let api = SparkAPI.current else { loading = false; return }
        do {
            let d = try await api.object("GET", "api/profile/mail/tree", query: fresh ? ["fresh": "true"] : [:], timeout: 60)
            accounts = (d["accounts"] as? [[String: Any]] ?? []).prefix(4).map { a -> Box in
                let id = a["id"] as? String ?? "", delim = a["delim"] as? String ?? "/"
                let fs = (a["folders"] as? [[String: Any]] ?? []).prefix(80).compactMap { f -> MailFolder? in
                    guard let n = f["name"] as? String, !n.isEmpty else { return nil }
                    let last = delim.isEmpty ? n : String(n.components(separatedBy: delim).last ?? n)
                    return MailFolder(account: id, name: n, title: n == "INBOX" ? String(localized: "Posteingang") : String(last.prefix(80)),
                                      role: f["role"] as? String ?? "folder", depth: f["depth"] as? Int ?? 0,
                                      unseen: f["unseen"] as? Int ?? 0, own: f["own"] as? Bool ?? false)
                }
                return Box(id: id, name: String((a["name"] as? String ?? "").prefix(60)), folders: Array(fs), error: a["error"] as? Bool ?? false)
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    private func save(_ n: (account: String, inside: String, folder: String)) async {
        naming = nil
        let v = name.trimmingCharacters(in: .whitespaces)
        guard !v.isEmpty, let api = SparkAPI.current else { return }
        do {
            if n.folder.isEmpty {
                _ = try await api.object("POST", "api/profile/mail/folder/new", body: ["account": n.account, "folder": n.inside, "name": v])
            } else {
                _ = try await api.object("POST", "api/profile/mail/folder/rename", body: ["account": n.account, "folder": n.folder, "name": v])
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        await load(fresh: true)
    }

    private func remove(_ f: MailFolder) async {
        removing = nil
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("POST", "api/profile/mail/folder/remove", body: ["account": f.account, "folder": f.name])
            error = nil
            if current?.id == f.id { pick(nil) }
        } catch {
            self.error = error.localizedDescription
        }
        await load(fresh: true)
    }
}

/// A mail rule (mailregeln.py, Mailclient Stufe B): Wenn sender, subject word, recipient, attachment; Dann folder,
/// read, flag, not in „Für dich“. The Spark checks every rule again; its words are compared, never run.
struct MailRule: Identifiable {
    var id = ""
    var account = ""
    var from = ""
    var subject = ""
    var to = ""
    var attach = false
    var folder = ""
    var read = false
    var flag = false
    var quiet = false
    var on = true
    var month = 0
    var box = ""
    var key = UUID()

    init(account: String = "", from: String = "") { self.account = account; self.from = from }

    init(_ d: [String: Any]) {
        let w = d["when"] as? [String: Any] ?? [:], t = d["then"] as? [String: Any] ?? [:]
        id = String((d["id"] as? String ?? "").prefix(20)); account = d["account"] as? String ?? ""
        from = String((w["from"] as? String ?? "").prefix(80)); subject = String((w["subject"] as? String ?? "").prefix(80))
        to = String((w["to"] as? String ?? "").prefix(80)); attach = w["attach"] as? Bool ?? false
        folder = String((t["folder"] as? String ?? "").prefix(200)); read = t["read"] as? Bool ?? false
        flag = t["flag"] as? Bool ?? false; quiet = t["quiet"] as? Bool ?? false
        on = d["on"] as? Bool ?? true; month = d["month"] as? Int ?? 0; box = String((d["box"] as? String ?? "").prefix(60))
    }

    var body: [String: Any] {
        ["id": id, "account": account, "on": on, "when": ["from": from, "subject": subject, "to": to, "attach": attach],
         "then": ["folder": folder, "read": read, "flag": flag, "quiet": quiet]]
    }

    var when: String {
        var p: [String] = []
        if !from.isEmpty { p.append((from.hasPrefix("@") ? String(localized: "Absender endet auf ") : String(localized: "Absender ist ")) + from) }
        if !subject.isEmpty { p.append(String(localized: "Betreff enthält ") + "„" + subject + "“") }
        if !to.isEmpty { p.append(String(localized: "an ") + to) }
        if attach { p.append(String(localized: "mit Anhang")) }
        return p.joined(separator: String(localized: " und "))
    }

    var then: String {
        var p: [String] = []
        if !folder.isEmpty { p.append("→ " + folder) }
        if read { p.append(String(localized: "gelesen")) }
        if flag { p.append("★") }
        if quiet { p.append(String(localized: "nicht in „Für dich“")) }
        return p.joined(separator: ", ")
    }
}

/// Regeln: the profile's mail rules (first that fits decides), the sender rules of „Mails aufräumen“ read only;
/// a rule made, changed, paused, moved up, deleted; after saving, „auch die vorhandenen“ with the code.
struct MailRules: View {
    let start: MailRule?
    @Environment(\.dismiss) private var dismiss
    @State private var rules: [MailRule] = []
    @State private var tidy: [String] = []
    @State private var accounts: [(String, String)] = []
    @State private var editing: MailRule?
    @State private var loading = true
    @State private var error: String?
    @State private var note: String?

    var body: some View {
        NavigationStack {
            List {
                if let note { Text(note).foregroundStyle(.secondary) }
                Section {
                    ForEach(rules) { r in
                        Button { editing = r } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: r.when).foregroundStyle(r.on ? Color.primary : Color.secondary)
                                Text(verbatim: r.then + (r.box.isEmpty ? "" : " · " + r.box)).font(.caption).foregroundStyle(.secondary)
                                Text(r.on ? LocalizedStringKey("Diesen Monat \(r.month)") : LocalizedStringKey("pausiert")).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            Button("Löschen", role: .destructive) { Task { await call("DELETE", "api/profile/mail/rules/\(r.id)", nil) } }
                            Button(r.on ? LocalizedStringKey("Pause") : LocalizedStringKey("Weiter")) {
                                var x = r; x.on.toggle(); Task { await call("POST", "api/profile/mail/rules", x.body) }
                            }
                            .tint(.orange)
                        }
                        .swipeActions(edge: .leading) {
                            if r.id != rules.first?.id {
                                Button("Nach oben") {
                                    var ids = rules.map(\.id)
                                    if let i = ids.firstIndex(of: r.id), i > 0 { ids.swapAt(i, i - 1) }
                                    Task { await call("POST", "api/profile/mail/rules/order", ["ids": ids]) }
                                }
                                .tint(.blue)
                            }
                        }
                    }
                    if !loading && rules.isEmpty { Text("Noch keine Regel. Am schnellsten geht es an einer Mail: „Regel daraus …“.").foregroundStyle(.secondary) }
                    Button("Neue Regel") { editing = MailRule(account: accounts.first?.0 ?? "") }
                } footer: {
                    Text("Die erste passende Regel entscheidet. Regeln nehmen neue Mails; gelöscht wird nie eine Mail.")
                }
                if !tidy.isEmpty {
                    Section("Aus „Mails aufräumen“") { ForEach(tidy, id: \.self) { Text(verbatim: $0) } }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .overlay { if loading && rules.isEmpty { LadeZeilen(rows: 4).padding() } }
            .navigationTitle("Regeln")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .task {
                await load()
                if let start, editing == nil { editing = start }
            }
            .sheet(item: $editing) { r in
                MailRuleForm(rule: r, accounts: accounts) { text in
                    editing = nil
                    note = text
                    Task { await load() }
                }
            }
        }
    }

    private func load() async {
        guard let api = SparkAPI.current else { loading = false; return }
        do {
            show(try await api.object("GET", "api/profile/mail/rules"))
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    private func show(_ d: [String: Any]) {
        rules = (d["rules"] as? [[String: Any]] ?? []).prefix(100).map { MailRule($0) }
        tidy = (d["tidy"] as? [[String: Any]] ?? []).prefix(300).map { x in
            String((x["match"] as? String ?? "").prefix(80)) + " → " + ((x["keep"] as? Bool ?? false) ? String(localized: "Posteingang") : String((x["folder"] as? String ?? "").prefix(80)))
        }
        accounts = (d["accounts"] as? [[String: Any]] ?? []).prefix(4).map { (String(($0["id"] as? String ?? "").prefix(9)), String(($0["name"] as? String ?? "").prefix(60))) }
    }

    private func call(_ method: String, _ path: String, _ body: [String: Any]?) async {
        guard let api = SparkAPI.current else { return }
        do {
            show(try await api.object(method, path, body: body))
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct MailRuleForm: View {
    @State var rule: MailRule
    let accounts: [(String, String)]
    let done: (String?) -> Void
    @State private var folders: [String] = []
    @State private var test: Int?
    @State private var busy = false
    @State private var error: String?
    @State private var offer: (id: String, n: Int)?
    @State private var applied: (n: Int, folder: String, moved: [[String: Any]])?

    var body: some View {
        NavigationStack {
            Form {
                Picker("Postfach", selection: $rule.account) {
                    Text("Alle Postfächer (ohne Ordner)").tag("")
                    ForEach(accounts, id: \.0) { a in Text(verbatim: a.1).tag(a.0) }
                }
                Section("Wenn") {
                    TextField("Absender (Adresse oder @domain)", text: $rule.from).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Betreff enthält", text: $rule.subject)
                    TextField("An (Adresse)", text: $rule.to).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.emailAddress)
                    Toggle("nur mit Anhang", isOn: $rule.attach)
                }
                Section("Dann") {
                    Picker("Verschieben nach", selection: $rule.folder) {
                        Text("– im Posteingang lassen –").tag("")
                        ForEach(folders, id: \.self) { f in Text(verbatim: f).tag(f) }
                    }
                    .disabled(rule.account.isEmpty)
                    Toggle("als gelesen markieren", isOn: $rule.read)
                    Toggle("Markieren", isOn: $rule.flag)
                    Toggle("nicht in „Für dich“", isOn: $rule.quiet)
                }
                Section {
                    Button("Probelauf") { Task { await dryRun() } }.disabled(busy)
                    if let test { Text("Trifft \(test) Mails im Posteingang der letzten 90 Tage.").foregroundStyle(.secondary) }
                }
                if let a = applied {
                    Section {
                        Text("Einsortiert: \(a.n) Mails.")
                        Button("Rückgängig") { Task { await undo(a.folder, a.moved) } }.disabled(busy)
                        Button("Fertig") { done(String(localized: "Einsortiert: \(a.n) Mails.")) }
                    }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle(rule.id.isEmpty ? "Neue Regel" : "Regel ändern")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { done(nil) } }
                ToolbarItem(placement: .confirmationAction) { Button("Sichern") { Task { await save() } }.disabled(busy) }
            }
            .task(id: rule.account) { await loadFolders() }
            .confirmationDialog("Auch die Mails einsortieren, die schon im Posteingang liegen?",
                                isPresented: Binding(get: { offer != nil }, set: { if !$0 { offer = nil } }), titleVisibility: .visible) {
                Button("Ja, jetzt einsortieren") { if let o = offer { Task { await apply(o.id) } } }
                Button("Nur neue Mails", role: .cancel) { done(String(localized: "Gesichert. Die Regel nimmt ab jetzt neue Mails.")) }
            } message: {
                if let o = offer { Text("Die Regel passt auf \(o.n) Mails. Danach geht „Rückgängig“.") }
            }
        }
    }

    private func loadFolders() async {
        guard !rule.account.isEmpty, let api = SparkAPI.current,
              let f = try? await api.object("GET", "api/profile/mail/folders", query: ["account": rule.account])
        else { folders = []; return }
        folders = (f["folders"] as? [String] ?? []).prefix(100).map { String($0) }
        if !rule.folder.isEmpty && !folders.contains(rule.folder) { rule.folder = "" }
    }

    private func dryRun() async -> Int? {
        guard let api = SparkAPI.current else { return nil }
        busy = true
        defer { busy = false }
        do {
            let d = try await api.object("POST", "api/profile/mail/rules/test", body: rule.body, timeout: 90)
            test = d["n"] as? Int ?? 0
            error = nil
            return test
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    private func save() async {
        guard let api = SparkAPI.current else { return }
        busy = true
        do {
            let d = try await api.object("POST", "api/profile/mail/rules", body: rule.body)
            busy = false
            error = nil
            let id = d["saved"] as? String ?? ""
            let n = rule.folder.isEmpty ? 0 : (test ?? (await dryRun()) ?? 0)
            if n > 0 && !id.isEmpty { offer = (id, n) } else { done(String(localized: "Gesichert. Die Regel nimmt ab jetzt neue Mails.")) }
        } catch {
            busy = false
            self.error = error.localizedDescription
        }
    }

    private func apply(_ id: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/mail/rules/\(id)/apply", body: [:], timeout: 120)
            applied = (d["n"] as? Int ?? 0, String((d["folder"] as? String ?? "").prefix(200)), (d["moved"] as? [[String: Any]] ?? []).prefix(4).map { $0 })
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// „Rückgängig“: the moved mails back to the inbox, per mailbox (the same way as after a Mehrfachauswahl).
    private func undo(_ folder: String, _ moved: [[String: Any]]) async {
        guard let api = SparkAPI.current, !folder.isEmpty else { done(nil); return }
        busy = true
        defer { busy = false }
        do {
            for m in moved {
                let mids = (m["mids"] as? [String] ?? []).prefix(50).map { String($0.prefix(300)) }
                _ = try await api.object("POST", "api/profile/mail/acts/back",
                                         body: ["account": String((m["acct"] as? String ?? "").prefix(20)), "folder": folder, "mids": mids])
            }
            done(String(localized: "Zurück im Posteingang. Die Regel bleibt für neue Mails."))
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct MailView: View {
    @ObservedObject private var talk = Conversation.shared
    @Environment(\.dismiss) private var dismiss
    let item: MailItem
    let box: String
    /// nil: the inbox; else the folder the mail is in (Ordner)
    let folder: MailFolder?
    let changed: () -> Void
    @State private var m: MailText?
    @State private var keptAt: Date?
    @State private var error: String?
    @State private var folders: [String] = []
    @State private var archive: String?
    @State private var busy = false
    @State private var note: String?
    @State private var writing: MailDraft?
    @State private var asEvent = false
    @State private var flaggedNow: Bool?
    @State private var ruleFrom: MailRule?
    @State private var file: URL?
    @State private var fetching: Int?
    private var flagged: Bool { flaggedNow ?? item.flagged }

    var body: some View {
        List {
            if let at = keptAt { StandNote(at: at, loading: true).listRowBackground(Color.clear) }
            if let m {
                Section {
                    Text(verbatim: m.subject.isEmpty ? String(localized: "(ohne Betreff)") : m.subject).font(.headline)
                    LabeledContent("Von") { Text(verbatim: m.from) }
                    if !m.to.isEmpty { LabeledContent("An") { Text(verbatim: m.to) } }
                    LabeledContent("Wann") { Text(m.date, format: .dateTime.weekday().day().month().hour().minute()) }
                    if !box.isEmpty { LabeledContent("Postfach") { Text(verbatim: box) } }
                    if !m.files.isEmpty && (m.parts.isEmpty || !talk.allowed.areas.contains("mailmanage")) {
                        LabeledContent("Anhänge") { Text(verbatim: m.files.joined(separator: ", ")) }
                    }
                }
                // Anhang laden (Mailclient Stufe C, with Mails ordnen): fetched only on a tap, shown by Quick Look
                if !m.parts.isEmpty && talk.allowed.areas.contains("mailmanage") {
                    Section("Anhänge") {
                        ForEach(m.parts, id: \.n) { f in
                            Button { Task { await fetch(f.n, f.name) } } label: {
                                HStack {
                                    Label { Text(verbatim: f.name) } icon: { Image(systemName: "paperclip") }
                                    Spacer()
                                    if fetching == f.n { ProgressView() } else { Text(verbatim: "\(f.kb) KB").font(.caption).foregroundStyle(.secondary) }
                                }
                            }
                            .disabled(fetching != nil)
                        }
                    }
                }
                // other people's words: plain text, no link and no picture opens
                Section { Text(verbatim: m.text.isEmpty ? String(localized: "(kein Text)") : m.text).textSelection(.enabled) }
                actions
            } else if error == nil {
                LadeZeilen(rows: 4)
            }
            if let note { Text(note).foregroundStyle(.secondary) }
            if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
        }
        .navigationTitle("Mail")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
        .sheet(item: $ruleFrom) { r in MailRules(start: r) }
        .sheet(isPresented: Binding(get: { file != nil }, set: { if !$0 { if let file { try? FileManager.default.removeItem(at: file) }; file = nil } })) {
            if let file { NavigationStack { QuickLookView(url: file).ignoresSafeArea() } }
        }
        .sheet(isPresented: $asEvent) {
            NavigationStack {
                List { Section("Als Termin") { QuickAdd(text: Self.topic(m?.subject ?? "")) {} } }
                    .navigationTitle("Termin aus der Mail")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { asEvent = false } } }
            }
        }
    }

    /// the subject without Re:, AW:, Fwd: … as the line for Schnell eintragen
    static func topic(_ s: String) -> String {
        String(s.replacingOccurrences(of: #"^((re|aw|antw|fwd?|wg)\s*:\s*)+"#, with: "", options: [.regularExpression, .caseInsensitive]).prefix(200))
    }

    @ViewBuilder private var actions: some View {
        let a = talk.allowed.areas
        if a.contains("calendar") {
            Section { Button("Als Termin") { asEvent = true } }
        }
        if a.contains("mailsend") || a.contains("mailmanage") {
            Section {
                if a.contains("mailsend"), let m {
                    Button("Antworten") {
                        writing = MailDraft(reply: m.id, to: PostView.address(m.from),
                                            subject: m.subject.lowercased().hasPrefix("re:") || m.subject.lowercased().hasPrefix("aw:") ? m.subject : "Re: " + m.subject)
                    }
                    Button("Weiterleiten") {
                        let low = m.subject.lowercased()
                        writing = MailDraft(subject: low.hasPrefix("fwd:") || low.hasPrefix("wg:") ? m.subject : "Fwd: " + m.subject,
                                            forward: m.id, folder: folder?.name ?? "INBOX", files: m.files)
                    }
                }
                if a.contains("mailmanage") {
                    Button(item.unread ? LocalizedStringKey("Als gelesen markieren") : LocalizedStringKey("Als ungelesen markieren")) { Task { await act(item.unread ? "read" : "unread", "") } }
                        .disabled(busy)
                    Button(flagged ? LocalizedStringKey("Markierung weg") : LocalizedStringKey("Markieren")) { Task { await act(flagged ? "unflag" : "flag", "") } }
                        .disabled(busy)
                    if let m {
                        Button("Regel daraus …") {
                            ruleFrom = MailRule(account: String(item.id.prefix(9)), from: PostView.address(m.from).lowercased())
                        }
                    }
                    if folder?.movable ?? true {
                        if archive != nil && archive != folder?.name { Button("Archivieren") { Task { await act("archive", "") } }.disabled(busy) }
                        let into = (folder == nil ? [] : ["INBOX"]) + folders.filter { $0 != folder?.name }
                        if !into.isEmpty {
                            Menu("Verschieben nach …") {
                                ForEach(into, id: \.self) { f in
                                    Button { Task { await act("move", f) } } label: { Text(verbatim: f == "INBOX" ? String(localized: "Posteingang") : f) }
                                }
                            }
                            .disabled(busy)
                        }
                    }
                }
            } footer: {
                if a.contains("mailmanage") { Text("Gelöscht wird nie. Im Panel holt „Rückgängig“ eine verschobene Mail sofort zurück.") }
            }
        }
    }

    private func fetch(_ n: Int, _ name: String) async {
        guard let api = SparkAPI.current else { return }
        fetching = n
        defer { fetching = nil }
        do {
            file = try await api.mailFile(item.id, folder: folder?.name ?? "INBOX", n: n, name: name)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func load() async {
        let kept = folder == nil ? SparkAPI.keptMail(item.id) : nil   // kept on the iPhone: inbox mails only
        if m == nil, let kept, let k = Merken.object(kept), let t = SparkAPI.mailText(k.d) {
            m = t
            keptAt = k.at
        }
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/mail/message",
                                         query: folder.map { ["id": item.id, "folder": $0.name] } ?? ["id": item.id], timeout: 60)
            m = SparkAPI.mailText(d)
            if let kept { Merken.keepObject(kept, d) }
            keptAt = nil
            error = nil
        } catch {
            if m == nil { self.error = error.localizedDescription }
        }
        if talk.allowed.areas.contains("mailsend"), m != nil {
            // Antwortvorschläge „1a“: prepared while the mail is open, „Antworten“ finds them ready on the Spark
            let id = item.id
            Task { _ = try? await api.object("POST", "api/profile/mail/suggest", body: ["id": id], timeout: 120) }
        }
        if talk.allowed.areas.contains("mailmanage"),
           let f = try? await api.object("GET", "api/profile/mail/folders", query: ["account": String(item.id.prefix(9))]) {
            folders = (f["folders"] as? [String] ?? []).prefix(100).map { String($0) }
            archive = f["archive"] as? String
        }
    }

    private func act(_ action: String, _ into: String) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.call("POST", "api/profile/mail/act",
                                   body: ["id": item.id, "action": action, "folder": into, "mid": "", "src": folder?.name ?? "INBOX"])
            if let kept = SparkAPI.keptMail(item.id) { Merken.drop(kept) }
            changed()
            if action == "read" || action == "unread" {
                note = action == "read" ? String(localized: "Als gelesen markiert.") : String(localized: "Als ungelesen markiert.")
            } else if action == "flag" || action == "unflag" {
                flaggedNow = action == "flag"
                note = action == "flag" ? String(localized: "Markiert.") : String(localized: "Markierung entfernt.")
            } else {
                dismiss()
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// A new mail or an answer: the form, then the Spark's preview sheet; only „Senden“ there sends (senden.py).
struct MailDraft: Identifiable {
    var reply = ""
    var to = ""
    var subject = ""
    /// Weiterleiten (Mailclient Stufe C): the mail below the own words; its attachments only when wanted
    var forward = ""
    var folder = "INBOX"
    var files: [String] = []
    let id = UUID()
}

struct MailWrite: View {
    @Environment(\.dismiss) private var dismiss
    let draft: MailDraft
    @State private var to = ""
    @State private var cc = ""
    @State private var subject = ""
    @State private var text = ""
    @State private var preview: [String: Any]?
    @State private var busy = false
    @State private var error: String?
    @State private var ideas: [(String, String)] = []   // Antwortvorschläge: (direction, text)
    @State private var ideasNote: String?
    @State private var picked: Int?
    @State private var withFiles = true
    private static let tones: [(String, LocalizedStringKey)] = [("kuerzer", "kürzer"), ("freundlicher", "freundlicher"),
                                                                ("foermlicher", "förmlicher"), ("uebersetzen", "auf Englisch")]

    var body: some View {
        NavigationStack {
            Form {
                if let p = preview {
                    Section {
                        LabeledContent("Von") { Text(verbatim: p["from"] as? String ?? "") }
                        LabeledContent("An") { Text(verbatim: (p["to"] as? [String] ?? []).joined(separator: ", ")) }
                        if let c = p["cc"] as? [String], !c.isEmpty { LabeledContent("Kopie") { Text(verbatim: c.joined(separator: ", ")) } }
                        LabeledContent("Betreff") { Text(verbatim: p["subject"] as? String ?? "") }
                        if let f = p["files"] as? [String], !f.isEmpty { LabeledContent("Anhänge") { Text(verbatim: f.prefix(20).joined(separator: ", ")) } }
                    } header: { Text("So geht die Mail raus") }
                    Section { Text(verbatim: p["text"] as? String ?? "") }
                    Section {
                        Button("Senden") { Task { await send() } }.disabled(busy)
                        Button("Ändern") { preview = nil }
                    }
                } else {
                    Section {
                        TextField("An", text: $to).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                        TextField("Kopie", text: $cc).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                        TextField("Betreff", text: $subject)
                    }
                    if !draft.reply.isEmpty {
                        Section {
                            if ideas.isEmpty {
                                Text(ideasNote.map { SparkAPI.way($0) } ?? String(localized: "Vorschläge kommen …")).foregroundStyle(.secondary)
                            }
                            ForEach(Array(ideas.enumerated()), id: \.offset) { i, x in
                                Button {
                                    text = x.1
                                    picked = i
                                } label: {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(verbatim: x.0).font(.caption.weight(.semibold)).foregroundStyle(.tint)
                                        Text(verbatim: x.1).foregroundStyle(.primary)
                                    }
                                }
                                .listRowBackground(picked == i ? Color.accentColor.opacity(0.12) : Color(.secondarySystemGroupedBackground))
                            }
                        } header: { Text("Vorschläge (nichts wird gesendet)") }
                    }
                    if !draft.forward.isEmpty && !draft.files.isEmpty {
                        Section {
                            Toggle("Anhänge mitschicken", isOn: $withFiles)
                        } footer: { Text(verbatim: draft.files.joined(separator: ", ")) }
                    }
                    Section {
                        TextEditor(text: $text).frame(minHeight: 180)
                        if !draft.reply.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack {
                                    ForEach(Self.tones, id: \.0) { t in
                                        Button(t.1) { Task { await tone(t.0) } }.buttonStyle(.bordered).disabled(busy || text.isEmpty)
                                    }
                                }
                            }
                        }
                    } footer: {
                        Text(draft.forward.isEmpty ? LocalizedStringKey("Erst die Vorschau zeigt, was rausgeht. Gesendet wird nur dort.")
                             : LocalizedStringKey("Deine Zeilen stehen über der weitergeleiteten Mail und dürfen leer bleiben. Gesendet wird nur aus der Vorschau."))
                    }
                    Section { Button("Vorschau") { Task { await look() } }.disabled(busy || (draft.forward.isEmpty && text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)) }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle(!draft.reply.isEmpty ? Text("Antworten") : !draft.forward.isEmpty ? Text("Weiterleiten") : Text("Neue Mail"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Verwerfen") { dismiss() } } }
            .onAppear { if to.isEmpty && subject.isEmpty { to = draft.to; subject = draft.subject } }
            .task { if !draft.reply.isEmpty && ideas.isEmpty { await suggest() } }
            .interactiveDismissDisabled(busy)
        }
    }

    private func look() async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        var b: [String: Any] = ["to": String(to.prefix(2000)), "cc": String(cc.prefix(2000)), "subject": String(subject.prefix(200)),
                                "text": String(text.prefix(20000))]
        if !draft.reply.isEmpty { b["reply"] = draft.reply }   // a new mail goes from the first mailbox (senden.py)
        if !draft.forward.isEmpty {                            // the mailbox of the forwarded mail (senden._forward)
            b["forward"] = draft.forward
            b["folder"] = draft.folder
            b["files"] = withFiles && !draft.files.isEmpty
        }
        do {
            preview = try await api.object("POST", "api/profile/mail/send/preview", body: b)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Antwortvorschläge (antwortvorschlag.py): three answers to pick; the Spark kept them while the mail was open
    private func suggest() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/mail/suggest", body: ["id": draft.reply], timeout: 120)
            ideas = (d["items"] as? [[String: Any]] ?? []).prefix(3).compactMap { x in
                guard let t = x["text"] as? String, !t.isEmpty else { return nil }
                return (String((x["label"] as? String ?? "").prefix(24)), String(t.prefix(2000)))
            }
        } catch {
            ideasNote = error.localizedDescription
        }
    }

    private func tone(_ art: String) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            let d = try await api.object("POST", "api/profile/mail/rewrite", body: ["text": String(text.prefix(20000)), "art": art], timeout: 120)
            if let t = d["text"] as? String, !t.isEmpty { text = String(t.prefix(20000)) }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func send() async {
        guard let api = SparkAPI.current, let token = preview?["token"] as? String else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.call("POST", "api/profile/mail/send", body: ["token": token], timeout: 120)
            dismiss()
        } catch {
            self.error = error.localizedDescription
            preview = nil
        }
    }
}
