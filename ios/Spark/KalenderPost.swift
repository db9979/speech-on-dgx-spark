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
}

struct MailItem: Identifiable, Hashable {
    let id: String
    let from: String
    let subject: String
    let date: Date
    var unread: Bool
    let box: Int
}

struct MailText {
    let id: String
    let from: String
    let to: String
    let subject: String
    let date: Date
    let text: String
    let files: [String]
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
                            unread: x["unread"] as? Bool ?? false, box: x["box"] as? Int ?? 0)
        }
        return (Array(items), d["boxes"] as? [String] ?? [], d["connected"] as? Bool ?? true, d["errors"] as? [String] ?? [])
    }

    static func mailText(_ m: [String: Any]) -> MailText? {
        guard let id = m["id"] as? String, isMail(id) else { return nil }
        return MailText(id: id, from: String((m["from"] as? String ?? "").prefix(150)), to: String((m["to"] as? String ?? "").prefix(200)),
                        subject: String((m["subject"] as? String ?? "").prefix(200)),
                        date: Date(timeIntervalSince1970: (m["date"] as? NSNumber)?.doubleValue ?? 0),
                        text: String((m["text"] as? String ?? "").prefix(20000)), files: (m["files"] as? [String] ?? []).prefix(20).map { String($0) })
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

struct KalenderDetail: View {
    @Environment(\.dismiss) private var dismiss
    let e: CalEvent
    let calendar: String
    let change: () -> Void
    let done: () -> Void
    @State private var asking = false
    @State private var busy = false
    @State private var error: String?

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

    func load(_ on: Bool) async {
        guard on else { Merken.drop("post"); Merken.dropAll("mail-"); items = []; loading = false; return }
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

    private func show(_ d: [String: Any]) {
        let r = SparkAPI.inbox(d)
        items = r.items; boxes = r.boxes; connected = r.connected; errors = r.errors
    }
}

struct PostView: View {
    @ObservedObject private var talk = Conversation.shared
    @StateObject private var m = PostModel()
    @State private var writing: MailDraft?

    var body: some View {
        List {
            if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
            if !m.connected {
                Text(SparkAPI.way(String(localized: "Noch kein Postfach verbunden. Im Panel unter E-Mail → Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder IMAP.")))
                    .foregroundStyle(.secondary)
            } else if !m.loading && m.items.isEmpty {
                Text("Keine Mail in den letzten 14 Tagen.").foregroundStyle(.secondary)
            }
            ForEach(m.items) { x in
                NavigationLink {
                    MailView(item: x, box: m.boxes.count > 1 && m.boxes.indices.contains(x.box) ? m.boxes[x.box] : "") {
                        Task { await m.load(true) }
                    }
                } label: { row(x) }
            }
            if !m.errors.isEmpty { Text("Nicht erreicht: \(m.errors.joined(separator: ", "))").foregroundStyle(.red) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("E-Mail")
        .toolbar {
            if talk.allowed.areas.contains("mailsend") && m.connected {
                ToolbarItem(placement: .primaryAction) {
                    Button { writing = MailDraft() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Neue Mail")
                }
            }
        }
        .refreshable { await m.load(talk.allowed.areas.contains("mail")) }
        .task { await m.load(talk.allowed.areas.contains("mail")) }
        .overlay { if m.loading && m.keptAt == nil { LadeZeilen(rows: 6).padding() } }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
    }

    private func row(_ x: MailItem) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Circle().fill(x.unread ? Color.accentColor : .clear).frame(width: 8, height: 8).padding(.top, 6)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(verbatim: Self.name(x.from)).fontWeight(x.unread ? .semibold : .regular).lineLimit(1)
                    Spacer()
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

struct MailView: View {
    @ObservedObject private var talk = Conversation.shared
    @Environment(\.dismiss) private var dismiss
    let item: MailItem
    let box: String
    let changed: () -> Void
    @State private var m: MailText?
    @State private var keptAt: Date?
    @State private var error: String?
    @State private var folders: [String] = []
    @State private var archive: String?
    @State private var busy = false
    @State private var note: String?
    @State private var writing: MailDraft?

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
                    if !m.files.isEmpty { LabeledContent("Anhänge") { Text(verbatim: m.files.joined(separator: ", ")) } }
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
    }

    @ViewBuilder private var actions: some View {
        let a = talk.allowed.areas
        if a.contains("mailsend") || a.contains("mailmanage") {
            Section {
                if a.contains("mailsend"), let m {
                    Button("Antworten") {
                        writing = MailDraft(reply: m.id, to: PostView.address(m.from),
                                            subject: m.subject.lowercased().hasPrefix("re:") || m.subject.lowercased().hasPrefix("aw:") ? m.subject : "Re: " + m.subject)
                    }
                }
                if a.contains("mailmanage") {
                    Button(item.unread ? LocalizedStringKey("Als gelesen markieren") : LocalizedStringKey("Als ungelesen markieren")) { Task { await act(item.unread ? "read" : "unread", "") } }
                        .disabled(busy)
                    if archive != nil { Button("Archivieren") { Task { await act("archive", "") } }.disabled(busy) }
                    if !folders.isEmpty {
                        Menu("Verschieben nach …") {
                            ForEach(folders, id: \.self) { f in Button { Task { await act("move", f) } } label: { Text(verbatim: f) } }
                        }
                        .disabled(busy)
                    }
                }
            } footer: {
                if a.contains("mailmanage") { Text("Gelöscht wird nie. Im Panel holt „Rückgängig“ eine verschobene Mail sofort zurück.") }
            }
        }
    }

    private func load() async {
        let kept = SparkAPI.keptMail(item.id)
        if m == nil, let kept, let k = Merken.object(kept), let t = SparkAPI.mailText(k.d) {
            m = t
            keptAt = k.at
        }
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/mail/message", query: ["id": item.id], timeout: 60)
            m = SparkAPI.mailText(d)
            if let kept { Merken.keepObject(kept, d) }
            keptAt = nil
            error = nil
        } catch {
            if m == nil { self.error = error.localizedDescription }
        }
        if talk.allowed.areas.contains("mailmanage"),
           let f = try? await api.object("GET", "api/profile/mail/folders", query: ["account": String(item.id.prefix(9))]) {
            folders = (f["folders"] as? [String] ?? []).prefix(100).map { String($0) }
            archive = f["archive"] as? String
        }
    }

    private func act(_ action: String, _ folder: String) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.call("POST", "api/profile/mail/act", body: ["id": item.id, "action": action, "folder": folder, "mid": ""])
            if let kept = SparkAPI.keptMail(item.id) { Merken.drop(kept) }
            changed()
            if action == "read" || action == "unread" {
                note = action == "read" ? String(localized: "Als gelesen markiert.") : String(localized: "Als ungelesen markiert.")
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

    var body: some View {
        NavigationStack {
            Form {
                if let p = preview {
                    Section {
                        LabeledContent("Von") { Text(verbatim: p["from"] as? String ?? "") }
                        LabeledContent("An") { Text(verbatim: (p["to"] as? [String] ?? []).joined(separator: ", ")) }
                        if let c = p["cc"] as? [String], !c.isEmpty { LabeledContent("Kopie") { Text(verbatim: c.joined(separator: ", ")) } }
                        LabeledContent("Betreff") { Text(verbatim: p["subject"] as? String ?? "") }
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
                    Section { TextEditor(text: $text).frame(minHeight: 180) } footer: {
                        Text("Erst die Vorschau zeigt, was rausgeht. Gesendet wird nur dort.")
                    }
                    Section { Button("Vorschau") { Task { await look() } }.disabled(busy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle(draft.reply.isEmpty ? Text("Neue Mail") : Text("Antworten"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Verwerfen") { dismiss() } } }
            .onAppear { if to.isEmpty && subject.isEmpty { to = draft.to; subject = draft.subject } }
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
        do {
            preview = try await api.object("POST", "api/profile/mail/send/preview", body: b)
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
