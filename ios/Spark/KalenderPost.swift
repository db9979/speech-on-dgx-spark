import SwiftUI
import WebKit

/// Kalender und E-Mail in der App (plan kalender-mail Stufe 4, Dominik 2026-10-19 „baue alle Stufen“): the same
/// pages as in the panel, with this iPhone's key (iphone.THINGS "calendar", "mail", "mailmanage", "mailsend" on the
/// Spark: each opens only with its own function released for the profile). Every rule stays on the Spark: which
/// appointment may change, where a new one may go, what a mail may be moved to, what goes out.
///
/// Kept on the iPhone (Merken.swift, 1b): the appointments of four weeks, the newest 50 mails of the inbox and up to
/// 20 opened mails with their text; deleted when the function goes off, on unpairing and for another profile.
/// Texts from mail are other people's words: shown as plain text, or (Apple-Stil „2a“) as the HTML the Spark cleaned
/// (mailansicht.py) in a web view without script that loads nothing from outside; a link opens only after the
/// question with its address.

// ---------------------------------------------------------------- the data
struct CalEvent: Identifiable, Hashable {
    let start: Date
    let end: Date
    let allday: Bool
    let title: String
    let location: String
    let cal: Int
    let edit: Bool
    var note = ""      // the appointment's own text, plain (calendars._note)
    var link = ""      // its web address, shown as text only
    var why = ""       // why it is read-only, a fixed word (calendars._why): abo, geteilt, lesen
    var alarm = 0      // minutes before the start of its alert, 0: none (kalserie.alarm_of)
    var people: [CalPerson] = []   // a list in the appointment, never an invitation (kalserie.people_of)
    var uid = ""       // a repeating one (Apple-Stil „5a“): its series, the original start and the rule
    var rid = 0
    var rule = ""      // daily, weekly, biweekly, monthly, yearly, custom
    var until = ""     // YYYY-MM-DD or empty
    var id: String { "\(cal)|\(Int(start.timeIntervalSince1970))|\(title)" }
    var series: Bool { rid != 0 && !uid.isEmpty }
}

struct CalPerson: Hashable {
    var name: String
    var mail: String
    var shown: String { name.isEmpty ? mail : "\(name) <\(mail)>" }
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
    /// Mails löschen: out of anything but the trash itself (postfach._source_del); in the trash only „Endgültig löschen“
    var deletable: Bool { !["trash", "all", "group"].contains(role) }
    var trash: Bool { role == "trash" }
}

/// Regel-Vorschlag (mailregeln.learn): the third move of one sender into one folder asks whether a rule should do it.
struct MailHint: Identifiable {
    let account: String
    let from: String
    let folder: String
    var id: String { account + "|" + from + "|" + folder }
    init?(_ d: Any?) {
        guard let d = d as? [String: Any], let a = d["account"] as? String, let f = d["from"] as? String,
              let o = d["folder"] as? String, !a.isEmpty, !f.isEmpty, !o.isEmpty else { return nil }
        account = String(a.prefix(20)); from = String(f.prefix(200)); folder = String(o.prefix(200))
    }
}

/// „Rückgängig“ right after a delete (or a move): the same mails by their Message-ID back where they were.
struct MailUndo {
    let account: String
    let folder: String
    let mids: [String]
    let src: String
    let text: String
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
    /// its Message-ID: „Endgültig löschen“ removes only the mail that still carries it
    var mid = ""
    /// Apple-Stil „2a“: the mail has an HTML part (shown formatted, mailansicht.py) and names pictures from outside
    var html = false
    var remote = 0
    /// Einladungen aus Mails: the mail carries an invitation (.ics) this profile may take (EinladungSection)
    var invite = false
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
                            edit: e["edit"] as? Bool ?? false, note: String((e["note"] as? String ?? "").prefix(2000)),
                            link: String((e["link"] as? String ?? "").prefix(300)), why: String((e["why"] as? String ?? "").prefix(20)),
                            alarm: min(40320, max(0, e["alarm"] as? Int ?? 0)),
                            people: (e["people"] as? [[String: Any]] ?? []).prefix(20).compactMap { p in
                                guard let m = p["mail"] as? String, m.contains("@") else { return nil }
                                return CalPerson(name: String((p["name"] as? String ?? "").prefix(80)), mail: String(m.prefix(254)))
                            },
                            uid: String((e["uid"] as? String ?? "").prefix(255)), rid: e["rid"] as? Int ?? 0,
                            rule: String((e["rule"] as? String ?? "").prefix(12)), until: String((e["until"] as? String ?? "").prefix(10)))
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

    /// the form's fields as the Spark's page form takes them (calendars.page_item); a move sends only these, the
    /// Spark keeps every other field as the calendar has it
    static func calFields(title: String, allday: Bool, start: Date, end: Date, location: String) -> [String: Any] {
        let endDay = Calendar.current.date(byAdding: .day, value: 1, to: end) ?? end   // all day: the end is the next day
        return ["title": String(title.prefix(200)), "allday": allday, "location": String(location.prefix(200)),
                "start": allday ? isoDay(start) : isoMinute(start), "end": allday ? isoDay(endDay) : isoMinute(end)]
    }

    /// Apple-Stil „4a“: repeat (kalserie.RULES), its end, alert, people, note and link next to the times
    static func calMore(rule: String, until: Date?, alarm: Int, people: [CalPerson], note: String, link: String) -> [String: Any] {
        ["rule": rule, "until": rule.isEmpty || rule == "custom" ? "" : until.map { isoDay($0) } ?? "", "alarm": alarm,
         "people": people.prefix(20).map { ["name": String($0.name.prefix(80)), "mail": String($0.mail.prefix(254))] },
         "note": String(note.prefix(2000)), "link": String(link.prefix(300))]
    }

    /// Schnell eintragen: one line as the form's fields (calendars.quick on the Spark, fixed rules, nothing saved)
    func quickEvent(_ text: String) async throws -> [String: Any] {
        try await object("GET", "api/profile/calendar/quick", query: ["text": String(text.prefix(200)), "tz": Self.zone])
    }

    /// the fields of an appointment as shown, moved by `days` (+1 Tag, +1 Woche)
    static func moved(_ e: CalEvent, days: Int) -> [String: Any] {
        let c = Calendar.current
        let s = c.date(byAdding: .day, value: days, to: e.start) ?? e.start
        let en = c.date(byAdding: .day, value: days, to: e.end) ?? e.end
        return calFields(title: e.title, allday: e.allday, start: s,
                         end: e.allday ? (c.date(byAdding: .day, value: -1, to: en) ?? s) : en, location: e.location)
    }

    /// a new appointment; the answer's token takes it back („Rückgängig“, calendars.keep_undo)
    func addEvent(_ fields: [String: Any], calendar: String) async throws -> String {
        var b = fields
        b["calendar"] = calendar
        b["tz"] = Self.zone
        return try await object("POST", "api/profile/calendar/event", body: b)["undo"] as? String ?? ""
    }

    /// change (new fields) or delete (nil) exactly the appointment shown; one of a series with its scope "one"
    /// („Nur dieser Termin“) or "future" („Alle künftigen“); 409 when it is no longer there like this
    func changeEvent(_ e: CalEvent, _ new: [String: Any]?, scope: String = "") async throws -> String {
        var b: [String: Any] = ["change": new == nil ? "delete" : "edit", "cal": e.cal, "title": e.title,
                                "start": Int(e.start.timeIntervalSince1970), "tz": Self.zone]
        if let new { b["new"] = new }
        if e.series { b["uid"] = e.uid; b["rid"] = e.rid; b["scope"] = scope }
        return try await object("PUT", "api/profile/calendar/event", body: b)["undo"] as? String ?? ""
    }

    /// „Rückgängig“: the Spark puts the appointment back as it was (for two minutes after the change)
    func undoEvent(_ token: String) async throws {
        _ = try await call("POST", "api/profile/calendar/undo", body: ["undo": String(token.prefix(40))])
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
                        }, mid: String((m["mid"] as? String ?? "").prefix(300)),
                        html: m["html"] as? Bool ?? false, remote: min(60, max(0, m["remote"] as? Int ?? 0)), invite: m["invite"] as? Bool ?? false)
    }

    /// One own mail formatted (mailansicht.py, app=true): the Spark's cleaned HTML with its attached pictures inside
    /// and its policy in the page; never more than 8 MB.
    func mailPage(_ id: String, folder: String) async throws -> String {
        var r = request("api/profile/mail/view")
        var c = URLComponents(url: base.appendingPathComponent("api/profile/mail/view"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "app", value: "true"), URLQueryItem(name: "folder", value: folder), URLQueryItem(name: "id", value: id)]
        r.url = c.url
        r.timeoutInterval = 60
        let (data, response) = try await Self.confirmed(r, code: nil)
        try Self.check(data, response)
        guard data.count <= 8 * 1024 * 1024 else { throw SparkError(message: String(localized: "Die Mail ist zu groß für die App.")) }
        return String(decoding: data, as: UTF8.self)
    }

    /// the name of an opened mail's kept page ("mail-" and its id with the colon as a dash)
    static func keptMail(_ id: String) -> String? { isMail(id) ? "mail-" + id.replacingOccurrences(of: ":", with: "-") : nil }
}

// ---------------------------------------------------------------- Kalender
/// Wie Apple Kalender (Apple-Stil „4a“ „5a“, Dominik 2026-10-20): the week strip with its day under it (swipe to the
/// next day, the strip to the next week) or the list; a tap shows the appointment, „Bearbeiten“ the form in groups;
/// a repeating one asks „Nur dieser Termin“ or „Alle künftigen“; „Rückgängig“ asks the Spark to put it back.
@MainActor
final class KalenderModel: ObservableObject {
    @Published var v = CalView()
    @Published var loading = true
    @Published var error: String?
    @Published var keptAt: Date?
    @Published var day = Calendar.current.startOfDay(for: Date())
    @Published var undo: CalUndo?
    private var from: Date?
    static let span = 28

    static func monday(_ d: Date) -> Date {
        let c = Calendar(identifier: .iso8601)
        return c.date(from: c.dateComponents([.yearForWeekOfYear, .weekOfYear], from: d)) ?? Calendar.current.startOfDay(for: d)
    }

    /// four weeks from the Monday of the day shown; only the four weeks from this week are kept on the iPhone
    func load(_ on: Bool) async {
        guard on else { Merken.drop("kalender"); v = CalView(); loading = false; return }
        let first = Self.monday(day)
        let here = first == Self.monday(Date())
        if here, loading, keptAt == nil, let k = Merken.object("kalender") {
            v = SparkAPI.calView(k.d)
            keptAt = k.at
        }
        guard let api = SparkAPI.current else { loading = false; return }
        do {
            let d: [String: Any]
            if here {
                d = try await Merken.timed("kalender") { try await api.calendarView(from: first, days: Self.span) }
                Merken.keepObject("kalender", d)
            } else {
                d = try await api.calendarView(from: first, days: Self.span)
            }
            v = SparkAPI.calView(d)
            from = first
            keptAt = nil
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// another day: within the loaded weeks at once, else its four weeks are asked for
    func show(_ d: Date) async {
        day = Calendar.current.startOfDay(for: d)
        if let f = from, day >= f, let e = Calendar.current.date(byAdding: .day, value: Self.span, to: f), day < e { return }
        await load(true)
    }

    func move(days n: Int) async {
        await show(Calendar.current.date(byAdding: .day, value: n, to: day) ?? day)
    }

    /// the appointments of one day (an all-day one on every day it covers), all-day ones first
    func events(on d: Date) -> [CalEvent] {
        let a = Calendar.current.startOfDay(for: d)
        let b = Calendar.current.date(byAdding: .day, value: 1, to: a) ?? a
        return v.events.filter { $0.start < b && max($0.end, $0.start.addingTimeInterval(60)) > a }
            .sorted { ($0.allday ? 0 : 1, $0.start) < ($1.allday ? 0 : 1, $1.start) }
    }

    /// the list: the days with appointments of the loaded weeks, from the day shown on
    var days: [(Date, [CalEvent])] {
        let groups = Dictionary(grouping: v.events) { Calendar.current.startOfDay(for: $0.start) }
        return groups.filter { $0.key >= day || $0.value.contains { $0.end > day } }
            .sorted { $0.key < $1.key }
            .map { ($0.key, $0.value.sorted { ($0.allday ? 0 : 1, $0.start) < ($1.allday ? 0 : 1, $1.start) }) }
    }

    func saved(_ token: String, _ text: String) {
        undo = token.isEmpty ? nil : CalUndo(token: token, text: text)
        Task { await load(true) }
    }

    func takeBack() async {
        guard let u = undo, let api = SparkAPI.current else { return }
        undo = nil
        do {
            try await api.undoEvent(u.token)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        await load(true)
    }
}

struct CalUndo {
    let token: String
    let text: String
}

/// repeat and alert as the app names them (kalserie.RULES, kalserie.ALARMS on the Spark)
enum CalNames {
    static let rules = ["", "daily", "weekly", "biweekly", "monthly", "yearly"]
    static let alarms = [0, 5, 10, 15, 30, 60, 120, 1440, 2880]

    static func rule(_ r: String) -> String {
        switch r {
        case "daily": return String(localized: "Täglich")
        case "weekly": return String(localized: "Wöchentlich")
        case "biweekly": return String(localized: "Alle 2 Wochen")
        case "monthly": return String(localized: "Monatlich")
        case "yearly": return String(localized: "Jährlich")
        case "custom": return String(localized: "Eigene Regel")
        default: return String(localized: "Nie")
        }
    }

    static func alarm(_ n: Int) -> String {
        if n <= 0 { return String(localized: "Keine") }
        if n % 1440 == 0 { return n == 1440 ? String(localized: "1 Tag vorher") : String(localized: "\(n / 1440) Tage vorher") }
        if n % 60 == 0 { return n == 60 ? String(localized: "1 Std. vorher") : String(localized: "\(n / 60) Std. vorher") }
        return String(localized: "\(n) Min. vorher")
    }

    /// "YYYY-MM-DD" (the end of a series as the Spark gives it) as a day here; nil when empty
    static func day(_ s: String) -> Date? {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return s.isEmpty ? nil : f.date(from: s)
    }

    /// "Anna <anna@example.org>" or "anna@example.org"; nil for anything else (the Spark checks again)
    static func person(_ s: String) -> CalPerson? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: ",;"))
        let mail = #"[^@\s<>",;]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}"#
        if let r = t.range(of: "^(.*?)\\s*<\\s*(" + mail + ")\\s*>$", options: .regularExpression) {
            let inner = String(t[r])
            guard let lt = inner.lastIndex(of: "<"), let gt = inner.lastIndex(of: ">") else { return nil }
            let name = inner[..<lt].trimmingCharacters(in: CharacterSet(charactersIn: " \""))
            return CalPerson(name: String(name.prefix(80)), mail: String(inner[inner.index(after: lt)..<gt]).trimmingCharacters(in: .whitespaces))
        }
        return t.range(of: "^" + mail + "$", options: .regularExpression) != nil ? CalPerson(name: "", mail: t) : nil
    }
}

struct KalenderView: View {
    @ObservedObject private var talk = Conversation.shared
    @StateObject private var m = KalenderModel()
    @State private var open: CalEvent?
    @State private var form: CalForm?
    @AppStorage("kalender.liste") private var asList = false

    var body: some View {
        List {
            if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
            if !m.v.connected {
                Text(SparkAPI.way(String(localized: "Noch kein Kalender verbunden. Im Panel unter Kalender → Einstellungen verbindest du iCloud, Nextcloud oder einen Abo-Link.")))
                    .foregroundStyle(.secondary)
            } else if asList {
                if !m.loading && m.days.isEmpty {
                    Text("In den nächsten vier Wochen steht nichts an.").foregroundStyle(.secondary)
                }
                ForEach(m.days, id: \.0) { day, evs in
                    Section {
                        ForEach(evs) { e in Button { open = e } label: { row(e) }.foregroundStyle(.primary) }
                    } header: {
                        Text(day, format: .dateTime.weekday(.wide).day().month(.wide))
                    }
                }
            } else {
                Section { WeekStrip(m: m) }
                Section {
                    let evs = m.events(on: m.day)
                    if evs.isEmpty && !m.loading { Text("Keine Termine").foregroundStyle(.secondary) }
                    ForEach(evs) { e in Button { open = e } label: { row(e) }.foregroundStyle(.primary) }
                } header: {
                    Text(m.day, format: .dateTime.weekday(.wide).day().month(.wide))
                }
            }
            if let u = m.undo {
                Section {
                    HStack {
                        Text(verbatim: u.text).lineLimit(2)
                        Spacer()
                        Button("Rückgängig") { Task { await m.takeBack() } }
                    }
                }
            }
            if !m.v.add.isEmpty {
                Section("Schnell eintragen") { QuickAdd(text: "") { token, title in m.saved(token, String(localized: "Eingetragen: \(title)")) } }
            }
            if !m.v.errors.isEmpty {
                Text("Nicht erreicht: \(m.v.errors.joined(separator: ", "))").foregroundStyle(.red)
            }
            if !m.v.notes.isEmpty {
                Text("Nicht gespeichert, der Kalender hat abgelehnt: \(m.v.notes.joined(separator: ", "))").foregroundStyle(.red)
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        // a swipe sideways turns the day (Apple Kalender); up and down still scrolls
        .simultaneousGesture(DragGesture(minimumDistance: 40).onEnded { g in
            guard !asList, abs(g.translation.width) > 90, abs(g.translation.height) < 50 else { return }
            Task { await m.move(days: g.translation.width < 0 ? 1 : -1) }
        })
        .navigationTitle("Kalender")
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("Heute") { Task { await m.show(Date()) } }
            }
            ToolbarItem(placement: .primaryAction) {
                Button { asList.toggle() } label: { Image(systemName: asList ? "calendar" : "list.bullet") }
                    .accessibilityLabel(asList ? Text("Tag zeigen") : Text("Liste zeigen"))
            }
            if !m.v.add.isEmpty {
                ToolbarItem(placement: .primaryAction) {
                    Button { form = CalForm(event: nil, day: m.day) } label: { Image(systemName: "plus") }
                        .accessibilityLabel("Neuer Termin")
                }
            }
        }
        .refreshable { await m.load(talk.allowed.areas.contains("calendar")) }
        .task { await m.load(talk.allowed.areas.contains("calendar")) }
        .overlay { if m.loading && m.keptAt == nil { LadeZeilen(rows: 5).padding() } }
        .sheet(item: $open) { e in
            KalenderDetail(e: e, calendar: m.v.calendars.indices.contains(e.cal) ? m.v.calendars[e.cal] : "",
                           change: { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { form = CalForm(event: e, day: m.day) } },
                           saved: { token, text in m.saved(token, text) })
        }
        .sheet(item: $form) { f in
            KalenderForm(event: f.event, day: f.day, calendars: m.v.add.compactMap { m.v.calendars.indices.contains($0) ? m.v.calendars[$0] : nil },
                         calendar: f.event.map { m.v.calendars.indices.contains($0.cal) ? m.v.calendars[$0.cal] : "" } ?? "") { token, text in
                m.saved(token, text)
            }
        }
    }

    private func row(_ e: CalEvent) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 2).fill(Self.tint(e.cal)).frame(width: 4)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    if !e.edit {
                        Image(systemName: "lock.fill").font(.caption2).foregroundStyle(.secondary).accessibilityLabel(Text("nur lesen"))
                    }
                    if !e.rule.isEmpty {
                        Image(systemName: "repeat").font(.caption2).foregroundStyle(.secondary).accessibilityLabel(Text("wiederholt sich"))
                    }
                    Text(verbatim: e.title.isEmpty ? String(localized: "(ohne Titel)") : e.title).lineLimit(2)
                }
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

/// The week of the day shown (Apple Kalender on the iPhone): a dot for a day with appointments; a tap shows that
/// day, a swipe on the strip the week before or after.
struct WeekStrip: View {
    @ObservedObject var m: KalenderModel

    var body: some View {
        let first = KalenderModel.monday(m.day)
        HStack(spacing: 2) {
            ForEach(0..<7, id: \.self) { i in
                let d = Calendar.current.date(byAdding: .day, value: i, to: first) ?? first
                let on = Calendar.current.isDate(d, inSameDayAs: m.day)
                let today = Calendar.current.isDateInToday(d)
                Button { Task { await m.show(d) } } label: {
                    VStack(spacing: 3) {
                        Text(d, format: .dateTime.weekday(.narrow)).font(.caption2).foregroundStyle(.secondary)
                        Text(d, format: .dateTime.day())
                            .font(.body.weight(on ? .semibold : .regular))
                            .frame(width: 34, height: 34)
                            .background(Circle().fill(on ? (today ? Color.red : Color.primary) : Color.clear))
                            .foregroundStyle(on ? Color(.systemBackground) : (today ? Color.red : Color.primary))
                        Circle().fill(m.events(on: d).isEmpty ? Color.clear : Color.secondary).frame(width: 5, height: 5)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(d, format: .dateTime.weekday(.wide).day().month(.wide)))
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance: 30).onEnded { g in
            guard abs(g.translation.width) > 60 else { return }
            Task { await m.move(days: g.translation.width < 0 ? 7 : -7) }
        })
    }
}

struct CalForm: Identifiable {
    let event: CalEvent?
    var day = Date()
    var id: String { event?.id ?? "neu" }
}

/// Schnell eintragen (Dominik 2026-10-19 „2a“, as on the page Kalender): one line; the Spark reads it with fixed
/// rules and shows what it understood, only „Eintragen“ saves (into the first own calendar, like the page).
/// `saved` gets the Spark's token for „Rückgängig“ and the title.
struct QuickAdd: View {
    @State var text: String
    let saved: (String, String) -> Void
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
            let token = try await api.addEvent(b, calendar: "")
            fields = nil
            text = ""
            done = true
            saved(token, f["title"] as? String ?? "")
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// One appointment as Apple Kalender shows it; „Bearbeiten“ opens the form. +1 Tag, +1 Woche and „Löschen“ of a
/// repeating one ask „Nur dieser Termin“ or „Alle künftigen“ (Apple-Stil „5a“); „Rückgängig“ is on the calendar.
struct KalenderDetail: View {
    @Environment(\.dismiss) private var dismiss
    let e: CalEvent
    let calendar: String
    let change: () -> Void
    let saved: (String, String) -> Void
    @State private var asking: Int?          // 0: delete, 1 or 7: move by that many days
    @State private var busy = false
    @State private var error: String?

    /// Why an appointment is read-only, from the panel's fixed word (calendars._why); the words are the app's own.
    static func readOnly(_ why: String) -> String {
        switch why {
        case "abo": return String(localized: "Nur lesen: der Kalender ist ein Abo-Link (iCal), Änderungen gehen nur beim Anbieter.")
        case "geteilt": return String(localized: "Nur lesen: ein Kalender, den dir jemand geteilt hat; ändern kann ihn nur, wem er gehört.")
        default: return String(localized: "Nur lesen: dieser Kalender lässt sich hier nicht ändern.")
        }
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
                }
                Section {
                    if !e.rule.isEmpty { LabeledContent("Wiederholen") { Text(CalNames.rule(e.rule)) } }
                    if e.alarm > 0 { LabeledContent("Erinnerung") { Text(CalNames.alarm(e.alarm)) } }
                    if !calendar.isEmpty { LabeledContent("Kalender") { Text(verbatim: calendar) } }
                    if !e.link.isEmpty { LabeledContent("Link") { Text(verbatim: e.link).textSelection(.enabled) } }
                }
                if !e.people.isEmpty {
                    Section("Personen") { ForEach(e.people, id: \.self) { Text(verbatim: $0.shown) } }
                }
                if !e.note.isEmpty {
                    Section("Notiz") { Text(verbatim: e.note).textSelection(.enabled) }   // plain text, no link opens
                }
                if e.edit {
                    Section {
                        Button("Bearbeiten") { dismiss(); change() }
                        HStack {
                            Button("+1 Tag") { ask(1) }.buttonStyle(.bordered)
                            Button("+1 Woche") { ask(7) }.buttonStyle(.bordered)
                        }
                        .disabled(busy)
                        Button("Termin löschen", role: .destructive) { asking = 0 }.disabled(busy)
                    }
                } else {
                    Section { Label { Text(Self.readOnly(e.why)) } icon: { Image(systemName: "lock") }.foregroundStyle(.secondary) }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle("Termin")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .confirmationDialog(asking == 0 ? Text("Termin löschen?") : Text("Termin verschieben?"),
                                isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } }),
                                titleVisibility: .visible, presenting: asking) { n in
                if e.series {
                    Button("Nur dieser Termin", role: n == 0 ? .destructive : nil) { Task { await run(n, "one") } }
                    Button("Alle künftigen", role: n == 0 ? .destructive : nil) { Task { await run(n, "future") } }
                } else {
                    if n == 0 {
                        Button("Löschen", role: .destructive) { Task { await run(0, "") } }
                    } else {
                        Button("Verschieben") { Task { await run(n, "") } }
                    }
                }
            }
        }
    }

    /// a move of a single appointment goes at once (Dominik 2026-10-19 „1a“); a series and every delete ask first
    private func ask(_ days: Int) {
        if e.series { asking = days } else { Task { await run(days, "") } }
    }

    private func run(_ days: Int, _ scope: String) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            let token = try await api.changeEvent(e, days == 0 ? nil : SparkAPI.moved(e, days: days), scope: scope)
            error = nil
            saved(token, days == 0 ? String(localized: "Gelöscht: \(e.title)") : String(localized: "Verschoben: \(e.title)"))
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// Neuer Termin / Termin bearbeiten in groups like Apple Kalender (Apple-Stil „4a“): title and place, the times,
/// repeat with its end, calendar, alert, people (a list in the appointment only: no invitation goes out), note and
/// link. A repeating one asks „Nur dieser Termin“ or „Alle künftigen“; a changed rule only „Alle künftigen“.
struct KalenderForm: View {
    @Environment(\.dismiss) private var dismiss
    let event: CalEvent?
    let day: Date
    let calendars: [String]
    let saved: (String, String) -> Void
    @State private var title = ""
    @State private var location = ""
    @State private var allday = false
    @State private var start = Date()
    @State private var end = Date().addingTimeInterval(3600)
    @State private var rule = ""
    @State private var ends = false
    @State private var until = Date()
    @State private var calendar = ""
    @State private var alarm = 0
    @State private var people: [CalPerson] = []
    @State private var person = ""
    @State private var note = ""
    @State private var link = ""
    @State private var asking = false
    @State private var busy = false
    @State private var error: String?

    /// the fields start as the appointment has them (or the day shown with the next full hour), set here and not
    /// on appear: the end follows a changed start, and that must not count the first filling
    init(event: CalEvent?, day: Date, calendars: [String], calendar: String, saved: @escaping (String, String) -> Void) {
        self.event = event
        self.day = day
        self.calendars = calendars
        self.saved = saved
        let c = Calendar.current
        if let e = event {
            _title = State(initialValue: e.title); _location = State(initialValue: e.location)
            _allday = State(initialValue: e.allday); _start = State(initialValue: e.start)
            _end = State(initialValue: e.allday ? (c.date(byAdding: .day, value: -1, to: e.end) ?? e.start) : e.end)
            _rule = State(initialValue: e.rule); _alarm = State(initialValue: e.alarm); _people = State(initialValue: e.people)
            _note = State(initialValue: e.note); _link = State(initialValue: e.link)
            let u = CalNames.day(e.until)
            _ends = State(initialValue: u != nil)
            _until = State(initialValue: u ?? e.start)
            _calendar = State(initialValue: calendar)
        } else {
            let now = Date()
            let hour = c.component(.hour, from: now.addingTimeInterval(3600))
            let s = c.date(bySettingHour: hour, minute: 0, second: 0, of: day) ?? now
            _start = State(initialValue: s)
            _end = State(initialValue: s.addingTimeInterval(3600))
            _until = State(initialValue: c.date(byAdding: .month, value: 3, to: s) ?? s)
            _calendar = State(initialValue: calendar.isEmpty ? calendars.first ?? "" : calendar)
        }
    }

    /// the rule or its end changed: only „Alle künftigen“ makes sense then
    private var ruleChanged: Bool {
        guard let e = event else { return false }
        return rule != e.rule || (ends ? SparkAPI.isoDay(until) : "") != e.until
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Titel", text: $title)
                    TextField("Ort", text: $location)
                }
                Section {
                    Toggle("Ganztägig", isOn: $allday)
                    DatePicker("Beginn", selection: $start, displayedComponents: allday ? [.date] : [.date, .hourAndMinute])
                    DatePicker("Ende", selection: $end, in: start..., displayedComponents: allday ? [.date] : [.date, .hourAndMinute])
                }
                Section {
                    Picker("Wiederholen", selection: $rule) {
                        ForEach(CalNames.rules + (rule == "custom" ? ["custom"] : []), id: \.self) { Text(CalNames.rule($0)).tag($0) }
                    }
                    if !rule.isEmpty && rule != "custom" {
                        Toggle("Endet", isOn: $ends)
                        if ends { DatePicker("Endet am", selection: $until, in: start..., displayedComponents: [.date]) }
                    }
                }
                if event == nil && calendars.count > 1 {
                    Section {
                        Picker("Kalender", selection: $calendar) {
                            ForEach(calendars, id: \.self) { Text(verbatim: $0).tag($0) }
                        }
                    }
                }
                Section {
                    Picker("Erinnerung", selection: $alarm) {
                        ForEach(CalNames.alarms + (CalNames.alarms.contains(alarm) ? [] : [alarm]), id: \.self) { Text(CalNames.alarm($0)).tag($0) }
                    }
                }
                Section {
                    ForEach(people, id: \.self) { Text(verbatim: $0.shown) }
                        .onDelete { people.remove(atOffsets: $0) }
                    if people.count < 20 {
                        HStack {
                            TextField("Name <mail@beispiel.de>", text: $person)
                                .textInputAutocapitalization(.never)
                                .keyboardType(.emailAddress)
                                .onSubmit { addPerson() }
                            Button { addPerson() } label: { Image(systemName: "plus.circle.fill") }
                                .accessibilityLabel("Person hinzufügen")
                                .disabled(CalNames.person(person) == nil)
                        }
                    }
                } header: {
                    Text("Personen")
                } footer: {
                    Text("Nur eine Liste im Termin: es geht keine Einladung raus.")
                }
                Section {
                    TextField("Notiz", text: $note, axis: .vertical).lineLimit(3...10)
                    TextField("Link", text: $link).textInputAutocapitalization(.never).keyboardType(.URL)
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle(event == nil ? Text("Neuer Termin") : Text("Termin bearbeiten"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        if event?.series == true { asking = true } else { Task { await save("") } }
                    } label: {
                        event == nil ? Text("Hinzufügen") : Text("Fertig")
                    }
                    .disabled(busy || title.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .confirmationDialog("Wiederholten Termin ändern?", isPresented: $asking, titleVisibility: .visible) {
                if !ruleChanged { Button("Nur dieser Termin") { Task { await save("one") } } }
                Button("Alle künftigen") { Task { await save("future") } }
            }
            .onChange(of: start) { old, s in
                // the end moves with the start, the length stays (Apple Kalender)
                end = max(s, end.addingTimeInterval(s.timeIntervalSince(old)))
            }
        }
    }

    private func addPerson() {
        guard let p = CalNames.person(person), !people.contains(where: { $0.mail.lowercased() == p.mail.lowercased() }) else { return }
        people.append(p)
        person = ""
    }

    private func save(_ scope: String) async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        if let p = CalNames.person(person) { people.append(p); person = "" }
        var fields = SparkAPI.calFields(title: title, allday: allday, start: start, end: end, location: location)
        fields.merge(SparkAPI.calMore(rule: rule, until: ends ? until : nil, alarm: alarm, people: people, note: note, link: link)) { a, _ in a }
        if event != nil && !ruleChanged { fields.removeValue(forKey: "rule"); fields.removeValue(forKey: "until") }
        do {
            let token: String
            if let e = event { token = try await api.changeEvent(e, fields, scope: scope) } else { token = try await api.addEvent(fields, calendar: calendar) }
            saved(token, event == nil ? String(localized: "Eingetragen: \(title)") : String(localized: "Geändert: \(title)"))
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
    /// after a delete or a move: one line, „Rückgängig“ and maybe the Regel-Vorschlag
    @Published var note: String?
    @Published var undo: MailUndo?
    @Published var hint: MailHint?
    /// Ältere nachladen (Dominik 2026-10-21 „1a 2a 5a“): the mark of the next older page (mail.more), "" at the end
    @Published var vor = ""
    @Published var more = false
    @Published var moreFail: String?
    @Published var moreErr: [String] = []
    /// Später senden (Dominik 2026-10-21 „4“): the planned mails, never their text
    @Published var later: [MailLater] = []

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
            await laterLoad()
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

    func laterLoad() async {
        guard let api = SparkAPI.current, Conversation.shared.allowed.areas.contains("mailsend") else { later = []; return }
        if let d = try? await api.object("GET", "api/profile/mail/later") {
            later = (d["items"] as? [[String: Any]] ?? []).prefix(40).compactMap(MailLater.init)
        }
    }

    /// a planned mail taken back (or a done line removed)
    func laterDrop(_ x: MailLater) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("DELETE", "api/profile/mail/later/\(x.id)")
            later = (d["items"] as? [[String: Any]] ?? []).prefix(40).compactMap(MailLater.init)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// swipe (Dominik 2026-10-19 „5a“): archive, delete, read or unread; the Spark decides what may happen (postfach.py)
    func act(_ x: MailItem, _ action: String) async {
        guard let api = SparkAPI.current else { return }
        let back = gone([x.id], action)
        do {
            let d = try await api.object("POST", "api/profile/mail/act",
                                         body: ["id": x.id, "action": action, "folder": "", "mid": "", "src": folder?.name ?? "INBOX"])
            if let kept = SparkAPI.keptMail(x.id) { Merken.drop(kept) }
            done(action, String(x.id.prefix(9)), d)
            error = nil
            if back.isEmpty { await load(true) }
        } catch {
            items += back.filter { b in !items.contains { $0.id == b.id } }
            self.error = error.localizedDescription
        }
    }

    /// Dominik 2026-10-21 „reloaded immer die gesamte Liste“: a mail moved, archived or deleted leaves the list at once
    /// and nothing is loaded anew (the page stays where it is, older pages too); what left comes back when the Spark says no
    func gone(_ ids: [String], _ action: String) -> [MailItem] {
        guard ["archive", "move", "delete", "erase"].contains(action) else { return [] }
        let out = items.filter { ids.contains($0.id) }
        items.removeAll { ids.contains($0.id) }
        return out
    }

    /// what the Spark answered to a delete, archive or move: the line with „Rückgängig“, the Regel-Vorschlag
    func done(_ action: String, _ account: String, _ d: [String: Any]) {
        hint = MailHint(d["hint"])
        let into = String((d["folder"] as? String ?? "").prefix(200))
        var mids = (d["mids"] as? [String] ?? []).prefix(50).map { String($0.prefix(300)) }
        if let m = d["mid"] as? String, !m.isEmpty { mids = [String(m.prefix(300))] }
        guard ["delete", "archive", "move"].contains(action), !into.isEmpty, !mids.isEmpty, !account.isEmpty else { undo = nil; return }
        let text = action == "delete" ? String(localized: "In den Papierkorb gelegt.") : String(localized: "Verschoben nach „\(into)“.")
        undo = MailUndo(account: account, folder: into, mids: mids, src: folder?.name ?? "INBOX", text: text)
        note = nil
    }

    /// „Rückgängig“: back by Message-ID (acts/back), from the folder or the trash they went into
    func back() async {
        guard let api = SparkAPI.current, let u = undo else { return }
        undo = nil
        hint = nil
        do {
            _ = try await api.object("POST", "api/profile/mail/acts/back", body: ["account": u.account, "folder": u.folder, "mids": u.mids, "src": u.src])
            note = String(localized: "Zurückgeholt.")
            error = nil
            await load(true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// the Regel-Vorschlag answered: "apply" (rule and the inbox now), "rule" (only the rule), "never" (not asked again)
    func answer(_ h: MailHint, _ how: String) async {
        hint = nil
        guard let api = SparkAPI.current else { return }
        do {
            if how == "never" {
                _ = try await api.object("POST", "api/profile/mail/rules/never", body: ["account": h.account, "from": h.from, "folder": h.folder])
                note = String(localized: "Gut, dafür frage ich nicht mehr.")
                return
            }
            let d = try await api.object("POST", "api/profile/mail/rules",
                                         body: ["account": h.account, "when": ["from": h.from], "then": ["folder": h.folder]])
            note = String(localized: "Regel angelegt: neue Mails von \(h.from) kommen nach „\(h.folder)“.")
            if how == "apply", let id = d["saved"] as? String, !id.isEmpty {
                let y = try await api.object("POST", "api/profile/mail/rules/\(id)/apply", body: [:], timeout: 120)
                note = (note ?? "") + " " + String(localized: "\(y["n"] as? Int ?? 0) Mails aus dem Posteingang dazu.")
                await load(true)
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Mehrfachauswahl: one action on every ticked mail (at most 50; a move goes into a folder of one mailbox)
    func actMany(_ action: String, _ into: String = "") async {
        guard let api = SparkAPI.current, !picked.isEmpty else { return }
        do {
            let ids = Array(picked.prefix(50)), back = gone(ids, action)
            let d: [String: Any]
            do {
                d = try await api.object("POST", "api/profile/mail/acts",
                                         body: ["ids": ids, "action": action, "folder": into, "src": folder?.name ?? "INBOX"])
            } catch {
                items += back.filter { b in !items.contains { $0.id == b.id } }
                throw error
            }
            for id in picked { if let kept = SparkAPI.keptMail(id) { Merken.drop(kept) } }
            // one mailbox moved: „Rückgängig“ as on the page; several mailboxes only the line
            let moved = (d["moved"] as? [[String: Any]] ?? [])
            if moved.count == 1, let m = moved.first {
                done(action, String((m["acct"] as? String ?? "").prefix(20)), ["folder": d["folder"] ?? "", "mids": m["mids"] ?? [String](), "hint": d["hint"] ?? NSNull()])
            } else {
                hint = MailHint(d["hint"])
                undo = nil
            }
            picked = []
            error = nil
            if back.isEmpty { await load(true) }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func show(_ d: [String: Any]) {
        let r = SparkAPI.inbox(d)
        items = r.items; boxes = r.boxes; connected = r.connected; errors = r.errors
        vor = String((d["vor"] as? String ?? "").prefix(200)); moreFail = nil; moreErr = []
    }

    /// at the end of the list: the next older page, in the inbox or the folder, with the search; never kept on the iPhone
    func older() async {
        guard !vor.isEmpty, !more, let api = SparkAPI.current else { return }
        more = true
        defer { more = false }
        let mark = vor
        var q = ["q": String(query.prefix(100)), "vor": mark]
        if let f = folder { q["account"] = f.account; q["folder"] = f.name }
        do {
            let d = try await api.object("GET", folder == nil ? "api/profile/mail/inbox" : "api/profile/mail/folder", query: q, timeout: 60)
            guard mark == vor else { return }   // the list was loaded anew meanwhile
            let r = SparkAPI.inbox(d), have = Set(items.map(\.id))
            items += r.items.filter { !have.contains($0.id) }
            items = Array(items.prefix(2000))
            vor = items.count >= 2000 ? "" : String((d["vor"] as? String ?? "").prefix(200))
            moreErr = r.errors
            moreFail = nil
        } catch {
            moreFail = error.localizedDescription
        }
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
    /// Mails löschen (own switch, off): only the person, into the mailbox's trash with „Rückgängig“
    private var del: Bool { manage && talk.allowed.areas.contains("maildelete") && (m.folder?.deletable ?? true) }
    /// the search words the Spark knows besides plain words (mail._words)
    private static let chips: [(String, LocalizedStringKey)] = [("ist:markiert", "★ Markiert"), ("hat:anhang", "📎 Mit Anhang"),
                                                                ("ist:ungelesen", "Ungelesen"), ("von:", "von: Absender"), ("betreff:", "betreff: Wort")]

    var body: some View {
        List(selection: $m.picked) {
            if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
            if m.undo != nil || m.note != nil || m.hint != nil { done }
            if !m.later.isEmpty {
                Section {
                    DisclosureGroup {
                        ForEach(m.later) { x in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: x.subject.isEmpty ? String(localized: "(ohne Betreff)") : x.subject)
                                Text(verbatim: String(localized: "an ") + x.to + " · " + x.at.formatted(.dateTime.weekday().day().month().hour().minute())
                                     + (x.state == "wartet" ? "" : " · " + x.stateText)).font(.caption).foregroundStyle(.secondary)
                            }
                            .swipeActions(edge: .trailing) {
                                Button(x.state == "wartet" ? LocalizedStringKey("Zurücknehmen") : LocalizedStringKey("Entfernen"), role: .destructive) {
                                    Task { await m.laterDrop(x) }
                                }
                            }
                        }
                    } label: {
                        let n = m.later.filter { $0.state == "wartet" }.count
                        Label(n == 1 ? LocalizedStringKey("1 Mail geplant") : n > 1 ? LocalizedStringKey("\(n) Mails geplant") : LocalizedStringKey("Geplante Mails"),
                              systemImage: "clock")
                    }
                }
            }
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
                            MailView(item: x, box: m.boxes.count > 1 && m.boxes.indices.contains(x.box) ? m.boxes[x.box] : "", folder: m.folder, post: m)
                        } label: { row(x) }
                        .swipeActions(edge: .trailing) {
                            if del {
                                Button(role: .destructive) { Task { await m.act(x, "delete") } } label: { Label("Löschen", systemImage: "trash") }
                            }
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
            if m.connected && !m.loading && (!m.vor.isEmpty || !m.items.isEmpty) {
                // one row of fixed height at the end (nothing jumps); it loads the older mails when it comes into view
                HStack(spacing: 8) {
                    Spacer()
                    if m.vor.isEmpty {
                        Text("Keine älteren Mails")
                    } else if m.more {
                        ProgressView()
                        Text("Lädt ältere Mails …")
                    } else if m.moreFail != nil {
                        Button("Nicht geladen, noch einmal") { Task { await m.older() } }
                    } else {
                        Text("Ältere Mails laden")
                    }
                    Spacer()
                }
                .font(.footnote).foregroundStyle(.secondary).frame(minHeight: 44)
                .listRowBackground(Color.clear)
                .onAppear { if m.moreFail == nil { Task { await m.older() } } }
            }
            if !m.moreErr.isEmpty { Text("Ältere Mails nicht erreicht: \(m.moreErr.joined(separator: ", "))").foregroundStyle(.red) }
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
                    if del { Button("Löschen", role: .destructive) { Task { await m.actMany("delete") } } }
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

    /// after a delete or move: the line, „Rückgängig“ and the Regel-Vorschlag with its three answers
    @ViewBuilder private var done: some View {
        Section {
            if let u = m.undo {
                HStack {
                    Text(verbatim: u.text)
                    Spacer()
                    Button("Rückgängig") { Task { await m.back() } }.buttonStyle(.borderless)
                }
            }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let h = m.hint {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Mails von \(h.from) legst du oft nach „\(h.folder)“. Soll eine Regel das übernehmen?")
                    Button("Regel anlegen und gleich anwenden") { Task { await m.answer(h, "apply") } }.buttonStyle(.borderedProminent)
                    HStack {
                        Button("Nur Regel") { Task { await m.answer(h, "rule") } }.buttonStyle(.bordered)
                        Button("Nicht mehr fragen") { Task { await m.answer(h, "never") } }.buttonStyle(.bordered)
                    }
                }
                .padding(.vertical, 4)
            }
        }
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
    @State private var sort = MailSortRun()
    @State private var sortAsk: String?

    var body: some View {
        NavigationStack {
            List {
                Button { pick(nil) } label: {
                    Label("Alle Posteingänge", systemImage: current == nil ? "tray.full.fill" : "tray.full")
                }
                if sort.shown { MailSortRow(run: sort, act: { k in if k == "go" || k == "back" { sortAsk = k } else { Task { await sortCall(k) } } }) }
                ForEach(accounts) { a in
                    Section {
                        if a.error { Text("Dieses Postfach war nicht erreichbar.").foregroundStyle(.red) }
                        ForEach(a.folders) { f in
                            Button { if f.role != "group" { pick(f) } } label: { row(f) }
                                .swipeActions(edge: .trailing) {
                                    if f.own {
                                        Button(role: .destructive) { removing = f } label: { Label("Entfernen", systemImage: "trash") }
                                        Button { name = f.title; naming = (f.account, "", f.name) } label: { Label("Umbenennen", systemImage: "pencil") }.tint(.blue)
                                    }
                                }
                                // like Apple Mail (Dominik 2026-10-21 „besser integriert“): long press, each with its symbol
                                .contextMenu {
                                    // Alle Mails hier einordnen (einordnen.py, Dominik 2026-10-24 „1-3“): first a proposal, nothing moves yet
                                    if ["inbox", "archive", "folder"].contains(f.role) {
                                        Button { Task { await sortCall("", body: ["account": f.account, "folder": f.name]) } } label: {
                                            Label("Alle Mails hier einordnen", systemImage: "tray.and.arrow.down")
                                        }
                                    }
                                    if sort.undo > 0 && !sort.going && sort.undoAccount == f.account && sort.undoFolder == f.name {
                                        Button { sortAsk = "back" } label: { Label("Einordnen rückgängig (\(sort.undo))", systemImage: "arrow.uturn.backward") }
                                    }
                                    if f.own {
                                        Button { name = f.title; naming = (f.account, "", f.name) } label: { Label("Umbenennen", systemImage: "pencil") }
                                    }
                                    if f.own || f.role == "inbox" {
                                        Button { name = ""; naming = (f.account, f.name, "") } label: { Label("Neuer Ordner darin", systemImage: "folder.badge.plus") }
                                    }
                                    if f.own {
                                        Divider()
                                        Button(role: .destructive) { removing = f } label: { Label("Ordner entfernen", systemImage: "trash") }
                                    }
                                }
                        }
                        Button("Neuer Ordner") { name = ""; naming = (a.id, "", "") }
                    } header: {
                        Text(verbatim: a.name)
                    } footer: {
                        Text("Lange drücken: alle Mails eines Ordners nach deinen Regeln einordnen. Eigene Ordner: wischen oder lange drücken zum Umbenennen oder Entfernen (nur leere). Ein Ordner mit Mails bleibt stehen.")
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
            .task { await sortLoad() }
            .confirmationDialog(sortAsk == "back" ? LocalizedStringKey("Alle Mails des letzten Einordnens zurückholen?") : LocalizedStringKey("Jetzt verschieben?"),
                                isPresented: Binding(get: { sortAsk != nil }, set: { if !$0 { sortAsk = nil } }), titleVisibility: .visible) {
                Button(sortAsk == "back" ? LocalizedStringKey("Zurückholen") : LocalizedStringKey("Verschieben")) { if let k = sortAsk { Task { await sortCall(k) } } }
            } message: {
                Text("Es wird nichts gelöscht, und „Rückgängig“ holt alles zurück.")
            }
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

    /// the folders of the mail program by their German (or English) name, as on the page (post.js POST_ROLE)
    static func roleName(_ role: String) -> String? {
        switch role {
        case "sent": return String(localized: "Gesendet")
        case "drafts": return String(localized: "Entwürfe")
        case "archive": return String(localized: "Archiv")
        case "trash": return String(localized: "Papierkorb")
        case "junk": return String(localized: "Spam")
        default: return nil
        }
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

    /// a kept list (Mail-Vorrat, Dominik 2026-10-21 „1“) comes at once with „neu“: asked again after 3 s, at most 5 times
    private func load(fresh: Bool, tries: Int = 0) async {
        guard let api = SparkAPI.current else { loading = false; return }
        var again = false
        do {
            let d = try await api.object("GET", "api/profile/mail/tree", query: fresh ? ["fresh": "true"] : [:], timeout: 60)
            again = d["neu"] as? Bool ?? false
            accounts = (d["accounts"] as? [[String: Any]] ?? []).prefix(4).map { a -> Box in
                let id = a["id"] as? String ?? "", delim = a["delim"] as? String ?? "/"
                let fs = (a["folders"] as? [[String: Any]] ?? []).prefix(80).compactMap { f -> MailFolder? in
                    guard let n = f["name"] as? String, !n.isEmpty else { return nil }
                    let last = delim.isEmpty ? n : String(n.components(separatedBy: delim).last ?? n)
                    let role = f["role"] as? String ?? "folder", depth = f["depth"] as? Int ?? 0
                    return MailFolder(account: id, name: n, title: n == "INBOX" ? String(localized: "Posteingang")
                                      : depth == 0 ? (Self.roleName(role) ?? String(last.prefix(80))) : String(last.prefix(80)),
                                      role: role, depth: depth,
                                      unseen: f["unseen"] as? Int ?? 0, own: f["own"] as? Bool ?? false)
                }
                return Box(id: id, name: String((a["name"] as? String ?? "").prefix(60)), folders: Array(fs), error: a["error"] as? Bool ?? false)
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
        if again && tries < 5 {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await load(fresh: false, tries: tries + 1)
        }
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

    /// the run of „Alle Mails hier einordnen“: asked again every 2 s while it goes
    private func sortLoad() async {
        guard let api = SparkAPI.current else { return }
        while !Task.isCancelled {
            guard let d = try? await api.object("GET", "api/profile/mail/einordnen") else { return }
            sort = MailSortRun(d)
            if !sort.going { return }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func sortCall(_ k: String, body: [String: Any] = [:]) async {
        sortAsk = nil
        guard let api = SparkAPI.current else { return }
        do {
            sort = MailSortRun(try await api.object("POST", "api/profile/mail/einordnen" + (k.isEmpty ? "" : "/" + k), body: body))
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        await sortLoad()
        if sort.state == "done" || sort.state == "stopped" { await load(fresh: true) }
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

/// Alle Mails hier einordnen (einordnen.py): the state of the run, numbers only; folder names come from the mail server.
struct MailSortRun {
    var kind = "", state = "", folder = "", err = ""
    var looked = 0, total = 0, stays = 0, moved = 0, undo = 0
    var undoFolder = ""
    var by: [(String, Int)] = []
    init() {}
    init(_ d: [String: Any]) {
        kind = d["kind"] as? String ?? ""
        state = d["state"] as? String ?? ""
        folder = d["folder"] as? String ?? ""
        err = d["err"] as? String ?? ""
        looked = d["looked"] as? Int ?? 0
        total = d["total"] as? Int ?? 0
        stays = d["stays"] as? Int ?? 0
        moved = d["moved"] as? Int ?? 0
        by = (d["by"] as? [[Any]] ?? []).prefix(20).compactMap { x in
            guard x.count == 2, let f = x[0] as? String, let n = x[1] as? Int else { return nil }
            return (String(f.prefix(80)), n)
        }
        if let u = d["undo"] as? [String: Any] {
            undo = u["n"] as? Int ?? 0
            undoFolder = u["folder"] as? String ?? ""
            undoAccount = u["account"] as? String ?? ""
        }
    }
    var going: Bool { ["scan", "move", "back"].contains(state) }
    var shown: Bool { !state.isEmpty }   // only while a run is there; „Rückgängig“ of the last run stays at its folder
    var undoAccount = ""
    var into: Int { by.reduce(0) { $0 + $1.1 } }
    static func name(_ f: String) -> String { f.isEmpty || f.uppercased() == "INBOX" ? String(localized: "Posteingang") : f }
}

struct MailSortRow: View {
    let run: MailSortRun
    let act: (String) -> Void

    var body: some View {
        Section("Einordnen") {
            Text(verbatim: line).font(.subheadline)
            if run.going { ProgressView().frame(maxWidth: .infinity, alignment: .leading) }
            if run.state == "ready" && run.into > 0 {
                Button { act("go") } label: { Label("\(run.into) verschieben", systemImage: "tray.and.arrow.down") }
            }
            if run.going {
                Button("Abbrechen", role: .destructive) { act("stop") }
            } else if !run.state.isEmpty {
                Button(run.state == "ready" && run.into > 0 ? LocalizedStringKey("Verwerfen") : LocalizedStringKey("Schließen")) { act("stop") }
            }
            if run.undo > 0 && !run.going {
                Button { act("back") } label: { Label("Rückgängig: \(run.undo) zurück", systemImage: "arrow.uturn.backward") }
            }
        }
    }

    private var line: String {
        let w = MailSortRun.name(run.folder)
        switch run.state {
        case "scan": return String(localized: "„\(w)“: \(run.looked) von \(min(run.total, 50000)) Mails angesehen …")
        case "ready":
            if run.into == 0 { return String(localized: "In „\(w)“ passt keine deiner Regeln: alle \(run.stays) Mails bleiben.") }
            let list = run.by.prefix(6).map { "\($0.1) → \(MailSortRun.name($0.0))" }.joined(separator: ", ")
            return String(localized: "Vorschlag für „\(w)“: \(list); \(run.stays) bleiben.")
        case "move": return String(localized: "Verschiebe: \(run.moved) von \(run.into) …")
        case "back": return String(localized: "Hole zurück: \(run.moved) von \(run.total) …")
        case "error": return run.err == "renumbered" ? String(localized: "Der Mail-Server hat den Ordner neu nummeriert, bitte noch einmal.")
            : String(localized: "Einordnen ging nicht, bitte noch einmal.")
        case "done", "stopped":
            return run.kind == "back" ? String(localized: "\(run.moved) Mails zurückgeholt.") : String(localized: "\(run.moved) Mails verschoben.")
        default: return String(localized: "Letztes Einordnen: \(run.undo) Mails, „Rückgängig“ holt sie zurück.")
        }
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
    var fixed = 0
    var paused = false
    var exceptions: [String] = []
    var key = UUID()

    init(account: String = "", from: String = "", subject: String = "") { self.account = account; self.from = from; self.subject = subject }

    init(_ d: [String: Any]) {
        let w = d["when"] as? [String: Any] ?? [:], t = d["then"] as? [String: Any] ?? [:]
        id = String((d["id"] as? String ?? "").prefix(20)); account = d["account"] as? String ?? ""
        from = String((w["from"] as? String ?? "").prefix(80)); subject = String((w["subject"] as? String ?? "").prefix(80))
        to = String((w["to"] as? String ?? "").prefix(80)); attach = w["attach"] as? Bool ?? false
        folder = String((t["folder"] as? String ?? "").prefix(200)); read = t["read"] as? Bool ?? false
        flag = t["flag"] as? Bool ?? false; quiet = t["quiet"] as? Bool ?? false
        on = d["on"] as? Bool ?? true; month = d["month"] as? Int ?? 0; box = String((d["box"] as? String ?? "").prefix(60))
        // Sortieren aus Korrekturen lernen (Stufe 3): corrections of 30 days, paused by them, the senders it leaves alone
        fixed = d["fixed"] as? Int ?? 0; paused = (d["paused"] as? Int ?? 0) > 0
        exceptions = (d["except"] as? [String] ?? []).prefix(50).map { String($0.prefix(200)) }
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
    @State private var suggest: [MailSuggestion] = []
    @State private var stats: MailStats?
    @State private var accounts: [(String, String)] = []
    @State private var learn = false
    @State private var fixes: [MailFix] = []
    @State private var editing: MailRule?
    @State private var loading = true
    @State private var error: String?
    @State private var note: String?

    var body: some View {
        NavigationStack {
            List {
                if let note { Text(note).foregroundStyle(.secondary) }
                // Regel-Vorschläge aus dem Ablegen (Dominik 2026-10-21 „ok“): a rule only after a tap
                if !suggest.isEmpty {
                    Section("Vorschläge aus deinem Ablegen") {
                        ForEach(suggest) { x in
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Mails von \(x.from)")
                                Text(x.inbox > 0 ? LocalizedStringKey("legst du in „\(x.folder)“ (\(x.n)×) · \(x.inbox) liegen gerade im Posteingang")
                                     : LocalizedStringKey("legst du in „\(x.folder)“ (\(x.n)×)")).font(.caption).foregroundStyle(.secondary)
                                HStack {
                                    Button(x.inbox > 0 ? LocalizedStringKey("Regel anlegen und ablegen") : LocalizedStringKey("Regel anlegen")) { Task { await take(x, x.inbox > 0) } }
                                        .buttonStyle(.borderedProminent)
                                    if x.inbox > 0 { Button("Nur Regel") { Task { await take(x, false) } }.buttonStyle(.bordered) }
                                    Button("Nicht mehr fragen") {
                                        Task {
                                            await call("POST", "api/profile/mail/rules/never", ["account": x.account, "from": x.from, "folder": x.folder])
                                            await load()
                                        }
                                    }
                                    .buttonStyle(.bordered)
                                }
                                .font(.caption)
                            }
                        }
                    }
                }
                // Korrekturen (30 Tage) (Sortieren aus Korrekturen lernen, Stufe 3): what you re-sorted after the Spark;
                // „Rückgängig“ takes back the exception or pause it made, no mail moves
                if learn && !fixes.isEmpty {
                    Section("Korrekturen (30 Tage)") {
                        ForEach(fixes) { x in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(verbatim: x.from.isEmpty ? "–" : x.from).lineLimit(1)
                                    Spacer()
                                    Text(x.stateKey).font(.caption2).foregroundStyle(x.state == "wartet" ? Color.orange : Color.secondary)
                                }
                                Text(verbatim: x.line).font(.caption).foregroundStyle(.secondary)
                                HStack {
                                    if x.undo && x.state != "wartet" {
                                        Button("Rückgängig") { Task { await call("POST", "api/profile/mail/rules/fixes/\(x.id)/undo", [:]) } }
                                            .buttonStyle(.bordered)
                                    }
                                    if let r = rules.first(where: { $0.id == x.rid }) {
                                        Button("Regel ändern") { editing = r }.buttonStyle(.bordered)
                                    }
                                }
                                .font(.caption)
                            }
                        }
                    }
                }
                Section {
                    ForEach(rules) { r in
                        Button { editing = r } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: r.when).foregroundStyle(r.on ? Color.primary : Color.secondary)
                                Text(verbatim: r.then + (r.box.isEmpty ? "" : " · " + r.box)).font(.caption).foregroundStyle(.secondary)
                                if learn {
                                    Text(r.on ? LocalizedStringKey("\(r.month) genommen · \(r.fixed) korrigiert") : LocalizedStringKey("pausiert · \(r.month) genommen · \(r.fixed) korrigiert"))
                                        .font(.caption2).foregroundStyle(r.on ? Color.secondary : Color.orange)
                                    if r.month + r.fixed > 0 {
                                        ProgressView(value: Double(r.month), total: Double(r.month + r.fixed)).tint(r.on ? Color.green : Color.orange)
                                    }
                                } else {
                                    Text(r.on ? LocalizedStringKey("Diesen Monat \(r.month)") : LocalizedStringKey("pausiert")).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            Button("Löschen", role: .destructive) { Task { await call("DELETE", "api/profile/mail/rules/\(r.id)", nil) } }
                            Button(r.on ? LocalizedStringKey("Pause") : (r.paused ? LocalizedStringKey("Wieder an") : LocalizedStringKey("Weiter"))) {
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
                // the exceptions of the rules (Sortieren aus Korrekturen lernen): removed one by one, the rule takes them again
                if learn && rules.contains(where: { !$0.exceptions.isEmpty }) {
                    Section {
                        ForEach(rules.filter { !$0.exceptions.isEmpty }) { r in
                            ForEach(r.exceptions, id: \.self) { a in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(verbatim: a).lineLimit(1)
                                        Text(verbatim: r.when).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                    }
                                    Spacer()
                                    Button("Entfernen") { Task { await call("POST", "api/profile/mail/rules/\(r.id)/except", ["from": a]) } }
                                        .buttonStyle(.bordered).font(.caption)
                                }
                            }
                        }
                    } header: {
                        Text("Ausnahmen der Regeln")
                    } footer: {
                        Text("Entfernt: die Regel nimmt neue Mails dieses Absenders wieder. Mails bleiben, wo sie sind.")
                    }
                }
                if !tidy.isEmpty {
                    Section("Aus „Mails aufräumen“") { ForEach(tidy, id: \.self) { Text(verbatim: $0) } }
                }
                // Mail-Statistik (mailregeln.stats, Dominik 2026-10-21 „6“): who writes most, mails a week; „Regel …“
                if let stats, stats.total > 0 {
                    Section {
                        DisclosureGroup {
                            HStack(spacing: 16) {
                                ForEach(Array(stats.weeks.enumerated()), id: \.offset) { i, n in
                                    VStack(alignment: .leading) {
                                        Text(verbatim: "\(n)").bold()
                                        Text(i == 0 ? LocalizedStringKey("diese Woche") : LocalizedStringKey("vor \(i) Wo.")).font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            ForEach(stats.senders) { x in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(verbatim: x.name.isEmpty ? x.addr : x.name)
                                        Text(x.unread > 0 ? LocalizedStringKey("\(x.n) Mails, \(x.unread) ungelesen") : LocalizedStringKey("\(x.n) Mails"))
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if x.rule {
                                        Text("hat Regel").font(.caption).foregroundStyle(.secondary)
                                    } else {
                                        Button("Regel …") { editing = MailRule(account: x.account.isEmpty ? (accounts.first?.0 ?? "") : x.account, from: x.addr) }
                                            .buttonStyle(.bordered).font(.caption)
                                    }
                                }
                            }
                        } label: {
                            Text("Wer schreibt dir am meisten (30 Tage, \(stats.total) Mails, \(stats.unread) ungelesen)")
                        }
                    }
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
        if let d = try? await api.object("GET", "api/profile/mail/stats"), d["loading"] == nil { stats = MailStats(d) }
    }

    private func show(_ d: [String: Any]) {
        rules = (d["rules"] as? [[String: Any]] ?? []).prefix(100).map { MailRule($0) }
        tidy = (d["tidy"] as? [[String: Any]] ?? []).prefix(300).map { x in
            String((x["match"] as? String ?? "").prefix(80)) + " → " + ((x["keep"] as? Bool ?? false) ? String(localized: "Posteingang") : String((x["folder"] as? String ?? "").prefix(80)))
        }
        accounts = (d["accounts"] as? [[String: Any]] ?? []).prefix(4).map { (String(($0["id"] as? String ?? "").prefix(9)), String(($0["name"] as? String ?? "").prefix(60))) }
        if let x = d["suggest"] as? [[String: Any]] { suggest = x.prefix(20).compactMap(MailSuggestion.init) }
        learn = d["learn"] as? Bool ?? false
        fixes = (d["fixes"] as? [[String: Any]] ?? []).prefix(100).compactMap(MailFix.init)
    }

    /// a suggestion taken: the rule, and with file also the mails of that sender in the inbox now (as on the page)
    private func take(_ x: MailSuggestion, _ file: Bool) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/mail/rules", body: ["account": x.account, "when": ["from": x.from], "then": ["folder": x.folder]])
            show(d)
            note = String(localized: "Regel angelegt: neue Mails von \(x.from) kommen nach „\(x.folder)“.")
            if file, let id = d["saved"] as? String, !id.isEmpty {
                let y = try await api.object("POST", "api/profile/mail/rules/\(id)/apply", body: [:], timeout: 120)
                note = (note ?? "") + " " + String(localized: "\(y["n"] as? Int ?? 0) Mails aus dem Posteingang dazu.")
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
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

/// Mail-Statistik (mailregeln.stats): mails a week, newest first, and who writes most; numbers and the own senders only
struct MailStats {
    struct Sender: Identifiable {
        let addr: String
        let name: String
        let n: Int
        let unread: Int
        let rule: Bool
        let account: String
        var id: String { addr }
    }
    let weeks: [Int]
    let senders: [Sender]
    let total: Int
    let unread: Int

    init(_ d: [String: Any]) {
        weeks = (d["weeks"] as? [Int] ?? []).prefix(8).map { $0 }
        senders = (d["senders"] as? [[String: Any]] ?? []).prefix(30).compactMap { x in
            guard let a = x["addr"] as? String, !a.isEmpty else { return nil }
            return Sender(addr: String(a.prefix(200)), name: String((x["name"] as? String ?? "").prefix(60)), n: x["n"] as? Int ?? 0,
                          unread: x["unread"] as? Int ?? 0, rule: x["rule"] as? Bool ?? false, account: String((x["acct"] as? String ?? "").prefix(9)))
        }
        total = d["total"] as? Int ?? 0
        unread = d["unread"] as? Int ?? 0
    }
}

/// A planned mail (Später senden, senden.later_list): when, to whom, subject, state; never its text
struct MailLater: Identifiable {
    let id: String
    let at: Date
    let to: String
    let subject: String
    let state: String

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, let at = d["at"] as? Int else { return nil }
        self.id = String(id.prefix(20))
        self.at = Date(timeIntervalSince1970: TimeInterval(at))
        to = String((d["to"] as? String ?? "").prefix(300))
        subject = String((d["subject"] as? String ?? "").prefix(200))
        state = String((d["state"] as? String ?? "").prefix(20))
    }

    var stateText: String {
        switch state {
        case "gesendet": return String(localized: "gesendet")
        case "nicht gesendet": return String(localized: "nicht gesendet")
        case "unklar": return String(localized: "unklar, schau in Gesendet")
        default: return String(localized: "wird gesendet")
        }
    }
}

/// One other mail of a conversation (mail.thread): who, when, its own text; own = sent from this mailbox
struct MailThreadItem: Identifiable {
    let id: String
    let from: String
    let date: Date
    let text: String
    let own: Bool

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String else { return nil }
        self.id = String(id.prefix(40)) + String((d["folder"] as? String ?? "").prefix(200))
        from = String((d["from"] as? String ?? "").prefix(150))
        date = Date(timeIntervalSince1970: TimeInterval(d["date"] as? Int ?? 0))
        text = String((d["text"] as? String ?? "").prefix(1500))
        own = d["own"] as? Bool ?? false
    }
}

/// A correction (mailregeln.fix_list, Sortieren aus Korrekturen lernen Stufe 3): a mail the Spark sorted that the person
/// put elsewhere; sender, from where to where, which rule or „Postfach aufräumen“, when, what became of it
struct MailFix: Identifiable {
    let id: String
    let from: String
    let von: String
    let nach: String
    let by: String
    let rid: String
    let rule: String
    let t: Int
    let state: String
    let undo: Bool

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, !id.isEmpty else { return nil }
        self.id = String(id.prefix(20))
        from = String((d["from"] as? String ?? "").prefix(200))
        von = String((d["von"] as? String ?? "").prefix(200))
        nach = String((d["nach"] as? String ?? "").prefix(200))
        by = d["by"] as? String ?? "rule"
        rid = String((d["rid"] as? String ?? "").prefix(20))
        rule = String((d["rule"] as? String ?? "").prefix(120))
        t = d["t"] as? Int ?? 0
        state = d["state"] as? String ?? ""
        undo = d["undo"] as? Bool ?? false
    }

    static func folder(_ f: String) -> String {
        if f.isEmpty { return String(localized: "Falsch sortiert") }
        if f.uppercased() == "INBOX" { return String(localized: "Posteingang") }
        return f
    }

    var line: String {
        let who = by == "tidy" ? String(localized: "Postfach aufräumen")
            : (rule.isEmpty ? String(localized: "Regel gelöscht") : String(localized: "Regel") + " „" + rule + "“")
        let day = Date(timeIntervalSince1970: TimeInterval(t)).formatted(date: .abbreviated, time: .omitted)
        return MailFix.folder(von) + " → " + MailFix.folder(nach) + " · " + who + " · " + day
    }

    var stateKey: LocalizedStringKey {
        switch state {
        case "wartet": return "wartet"
        case "ausnahme": return "Ausnahme gesetzt"
        case "pausiert": return "Regel pausiert"
        case "zurueck": return "zurückgenommen"
        default: return "nicht wieder verschoben"
        }
    }
}

/// A rule the night found in the folders below the KI folder (mailregeln.suggest): sender (or @domain), folder, how often
struct MailSuggestion: Identifiable {
    let id: String
    let account: String
    let from: String
    let folder: String
    let n: Int
    let inbox: Int

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, let from = d["from"] as? String, let folder = d["folder"] as? String else { return nil }
        self.id = String(id.prefix(20))
        account = String((d["account"] as? String ?? "").prefix(20))
        self.from = String(from.prefix(120))
        self.folder = String(folder.prefix(200))
        n = d["n"] as? Int ?? 0
        inbox = d["inbox"] as? Int ?? 0
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
            var n = 0
            if !rule.folder.isEmpty {
                if let test { n = test } else { n = await dryRun() ?? 0 }
            }
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
    /// the list: it reloads and shows „Rückgängig“ and the Regel-Vorschlag after a delete or move
    let post: PostModel
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
    @State private var erasing = false
    @State private var page: String?
    @State private var pageHeight: CGFloat = 120
    @State private var thread: [MailThreadItem] = []
    @State private var linkAsk: URL?
    @Environment(\.colorScheme) private var scheme
    private var flagged: Bool { flaggedNow ?? item.flagged }

    var body: some View {
        List {
            if let at = keptAt { StandNote(at: at, loading: true).listRowBackground(Color.clear) }
            if let m {
                Section {
                    // the head like Apple Mail: the sender's circle, name and time, address and to whom, the subject big
                    HStack(alignment: .top, spacing: 12) {
                        Text(verbatim: PostView.initials(m.from)).font(.headline).foregroundStyle(.white)
                            .frame(width: 44, height: 44).background(Circle().fill(KalenderView.tint(m.from.unicodeScalars.reduce(0) { $0 &+ Int($1.value) })))
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(verbatim: PostView.name(m.from)).font(.headline).lineLimit(2)
                                Spacer(minLength: 8)
                                Text(m.date, format: .dateTime.day().month().hour().minute()).font(.caption).foregroundStyle(.secondary)
                            }
                            Text(verbatim: PostView.address(m.from)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                            if !m.to.isEmpty { Text(verbatim: String(localized: "An: ") + m.to).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        }
                    }
                    Text(verbatim: m.subject.isEmpty ? String(localized: "(ohne Betreff)") : m.subject).font(.title3.weight(.bold))
                    if !box.isEmpty { LabeledContent("Postfach") { Text(verbatim: box) } }
                    if !m.files.isEmpty && (m.parts.isEmpty || !talk.allowed.areas.contains("mailmanage")) {
                        LabeledContent("Anhänge") { Text(verbatim: m.files.joined(separator: ", ")) }
                    }
                }
                if m.invite && talk.allowed.areas.contains("einladungen") { EinladungSection(id: m.id, folder: folder?.name ?? "") }   // Einladung.swift
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
                // other people's words: formatted as the Spark cleaned them (nothing runs, nothing loads from outside,
                // a link asks first), else plain text
                if m.html, let page {
                    if m.remote > 0 {
                        Label("Bilder von außen bleiben in der App aus, damit der Absender nicht sieht, dass du die Mail liest.", systemImage: "lock")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    Section {
                        MailPageView(html: page, dark: scheme == .dark, height: $pageHeight) { url in
                            if url.scheme?.lowercased() == "mailto" {
                                let to = String(url.absoluteString.dropFirst(7).prefix { $0 != "?" }).removingPercentEncoding ?? ""
                                if talk.allowed.areas.contains("mailsend") { writing = MailDraft(to: String(to.prefix(2000))) }
                            } else { linkAsk = url }
                        }
                            .frame(height: pageHeight)
                            .listRowInsets(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
                    }
                } else {
                    Section { Text(verbatim: m.text.isEmpty ? String(localized: "(kein Text)") : m.text).textSelection(.enabled) }
                }
                // Unterhaltung (Dominik 2026-10-21 „1“): the other mails of the conversation, folded to one line each
                if !thread.isEmpty {
                    Section(thread.count == 1 ? LocalizedStringKey("Unterhaltung · 1 weitere Mail") : LocalizedStringKey("Unterhaltung · \(thread.count) weitere Mails")) {
                        ForEach(thread) { x in
                            DisclosureGroup {
                                Text(verbatim: x.text.isEmpty ? String(localized: "(kein Text)") : x.text).textSelection(.enabled)
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(alignment: .firstTextBaseline) {
                                        Text(verbatim: x.own ? String(localized: "Du") : PostView.name(x.from)).font(.subheadline.weight(.semibold))
                                        Spacer(minLength: 8)
                                        Text(x.date, format: .dateTime.day().month().hour().minute()).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Text(verbatim: x.text.replacingOccurrences(of: "\n", with: " ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                }
                            }
                        }
                    }
                }
                actions
            } else if error == nil {
                LadeZeilen(rows: 4)
            }
            if let note { Text(note).foregroundStyle(.secondary) }
            if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
        }
        .navigationTitle("Mail")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { bars }
        .task { await load() }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
        .sheet(item: $ruleFrom) { r in MailRules(start: r) }
        .sheet(isPresented: Binding(get: { file != nil }, set: { if !$0 { if let file { try? FileManager.default.removeItem(at: file) }; file = nil } })) {
            if let file { NavigationStack { QuickLookView(url: file).ignoresSafeArea() } }
        }
        .sheet(isPresented: $asEvent) {
            NavigationStack {
                List { Section("Als Termin") { QuickAdd(text: Self.topic(m?.subject ?? "")) { _, _ in } } }
                    .navigationTitle("Termin aus der Mail")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { asEvent = false } } }
            }
        }
        // a link of the mail: its real address first, Safari only after „Öffnen“; mailto: opens a new mail
        .confirmationDialog(Text(verbatim: String(localized: "Link öffnen? Er führt zu ") + (linkAsk?.host ?? "")),
                            isPresented: Binding(get: { linkAsk != nil }, set: { if !$0 { linkAsk = nil } }), titleVisibility: .visible) {
            Button("Öffnen") { if let u = linkAsk { UIApplication.shared.open(u) }; linkAsk = nil }
        } message: {
            Text(verbatim: String((linkAsk?.absoluteString ?? "").prefix(300)))
        }
        .confirmationDialog("Diese Mail endgültig löschen?", isPresented: $erasing, titleVisibility: .visible) {
            Button("Endgültig löschen", role: .destructive) { Task { await act("erase", "") } }
        } message: {
            Text("Sie ist danach auch im Postfach weg. Das lässt sich nicht rückgängig machen.")
        }
    }

    /// the subject without Re:, AW:, Fwd: … as the line for Schnell eintragen
    static func topic(_ s: String) -> String {
        String(s.replacingOccurrences(of: #"^((re|aw|antw|fwd?|wg)\s*:\s*)+"#, with: "", options: [.regularExpression, .caseInsensitive]).prefix(200))
    }

    // the buttons of a mail (Dominik 2026-10-20 „1 und 3“): the five most used at the thumb below, ★ and ⋯ on top
    private var into: [String] { (folder == nil ? [] : ["INBOX"]) + folders.filter { $0 != folder?.name } }
    private var canMove: Bool { folder?.movable ?? true }

    @ViewBuilder private var actions: some View {
        if talk.allowed.areas.contains("mailmanage") {
            Section {} footer: {
                talk.allowed.areas.contains("maildelete")
                    ? Text("Löschen legt die Mail in den Papierkorb, „Rückgängig“ holt sie zurück. Endgültig nur im Papierkorb nach Rückfrage.")
                    : Text("Gelöscht wird nie. „Rückgängig“ holt eine verschobene Mail sofort zurück.")
            }
        }
    }

    @ToolbarContentBuilder private var bars: some ToolbarContent {
        let a = talk.allowed.areas
        ToolbarItemGroup(placement: .topBarTrailing) {
            if a.contains("mailmanage") && m != nil {
                Button { Task { await act(flagged ? "unflag" : "flag", "") } } label: {
                    Image(systemName: flagged ? "star.fill" : "star")
                }
                .accessibilityLabel(flagged ? Text("Markierung weg") : Text("Markieren"))
                .disabled(busy)
            }
            if m != nil && (a.contains("mailmanage") || a.contains("mailsend")) {
                Menu {
                    if a.contains("mailsend") { Button { writing = MailDraft() } label: { Label("Neue Mail", systemImage: "square.and.pencil") } }
                    if a.contains("mailmanage") {
                        Button { Task { await act(item.unread ? "read" : "unread", "") } } label: {
                            Label(item.unread ? LocalizedStringKey("Als gelesen markieren") : LocalizedStringKey("Als ungelesen markieren"), systemImage: "envelope")
                        }
                        Button { rule() } label: { Label("Regel daraus …", systemImage: "gearshape") }
                    }
                } label: { Image(systemName: "ellipsis.circle") }
                .accessibilityLabel(Text("Mehr"))
            }
        }
        ToolbarItemGroup(placement: .bottomBar) {
            if m != nil {
                if a.contains("mailsend") {
                    Button { reply() } label: { Label("Antworten", systemImage: "arrowshape.turn.up.left") }
                    Spacer()
                    Button { forward() } label: { Label("Weiterleiten", systemImage: "arrowshape.turn.up.right") }
                    Spacer()
                }
                if a.contains("mailmanage") && canMove {
                    if archive != nil && archive != folder?.name {
                        Button { Task { await act("archive", "") } } label: { Label("Archivieren", systemImage: "archivebox") }.disabled(busy)
                        Spacer()
                    }
                    if !into.isEmpty {
                        Menu {
                            ForEach(into, id: \.self) { f in
                                Button { Task { await act("move", f) } } label: { Text(verbatim: f == "INBOX" ? String(localized: "Posteingang") : f) }
                            }
                        } label: { Label("Verschieben nach …", systemImage: "folder") }
                        .disabled(busy)
                        Spacer()
                    }
                }
                if a.contains("calendar") {
                    Button { asEvent = true } label: { Label("Als Termin", systemImage: "calendar.badge.plus") }
                }
                if a.contains("mailmanage") && a.contains("maildelete") {
                    if folder?.trash == true {
                        Spacer()
                        Button(role: .destructive) { erasing = true } label: { Label("Endgültig löschen", systemImage: "trash.slash") }.disabled(busy || m?.mid.isEmpty != false)
                    } else if folder?.deletable ?? true {
                        Spacer()
                        Button(role: .destructive) { Task { await act("delete", "") } } label: { Label("Löschen", systemImage: "trash") }.disabled(busy)
                    }
                }
            }
        }
    }

    private func reply() {
        guard let m else { return }
        let low = m.subject.lowercased()
        writing = MailDraft(reply: m.id, to: PostView.address(m.from),
                            subject: low.hasPrefix("re:") || low.hasPrefix("aw:") ? m.subject : "Re: " + m.subject)
    }

    private func forward() {
        guard let m else { return }
        let low = m.subject.lowercased()
        writing = MailDraft(subject: low.hasPrefix("fwd:") || low.hasPrefix("wg:") ? m.subject : "Fwd: " + m.subject,
                            forward: m.id, folder: folder?.name ?? "INBOX", files: m.files)
    }

    private func rule() {
        guard let m else { return }
        ruleFrom = MailRule(account: String(item.id.prefix(9)), from: PostView.address(m.from).lowercased(),
                            subject: String(Self.topic(m.subject).prefix(80)))
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
            // Tagesaktuell (Dominik 2026-10-21): an opened mail counts as read, like Apple Mail; only with Mails ordnen
            if item.unread, talk.allowed.areas.contains("mailmanage") {
                let id = item.id, src = folder?.name ?? "INBOX"
                Task {
                    if (try? await api.object("POST", "api/profile/mail/act",
                                              body: ["id": id, "action": "read", "folder": "", "mid": "", "src": src])) != nil {
                        await post.load(true)
                    }
                }
            }
        } catch {
            if m == nil { self.error = error.localizedDescription }
        }
        if m?.html == true, page == nil {   // the formatted copy; without it the plain text stays
            page = try? await api.mailPage(item.id, folder: folder?.name ?? "INBOX")
        }
        if m != nil, let t = try? await api.object("GET", "api/profile/mail/thread",
                                                   query: folder.map { ["id": item.id, "folder": $0.name] } ?? ["id": item.id], timeout: 60) {
            thread = (t["items"] as? [[String: Any]] ?? []).prefix(10).compactMap(MailThreadItem.init)
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
            var b: [String: Any] = ["id": item.id, "action": action, "folder": into, "mid": "", "src": folder?.name ?? "INBOX"]
            if action == "erase" { b["mid"] = m?.mid ?? ""; b["sure"] = true }   // only after the question below
            let d = try await api.object("POST", "api/profile/mail/act", body: b)
            if let kept = SparkAPI.keptMail(item.id) { Merken.drop(kept) }
            post.done(action, String(item.id.prefix(9)), d)
            if action == "erase" { post.note = String(localized: "Endgültig gelöscht.") }
            if post.gone([item.id], action).isEmpty { Task { await post.load(true) } }
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

/// A mail formatted (Apple-Stil „2a“): the page the Spark cleaned, in a web view that runs no script of the page, loads
/// nothing from the network (a content rule blocks every http, https and ftp load, the page carries its own policy) and
/// keeps no data; every tap on a link is stopped and handed to `link` (the question with its address), never followed.
struct MailPageView: UIViewRepresentable {
    let html: String
    /// dark mode: a plain mail (no colours of its own) in light letters on the list's own background, like Apple Mail;
    /// a mail with its own colours keeps its white page
    var dark = false
    @Binding var height: CGFloat
    let link: (URL) -> Void
    private static var rules: WKContentRuleList?
    /// WebKit's rules know no „|“: a filter with one compiled to nothing and the mail stayed empty (Dominik 2026-10-21)
    private static let block = "[" + ["^https?:", "^ftp:", "^wss?:"].map { #"{"trigger":{"url-filter":"\#($0)"},"action":{"type":"block"}}"# }
        .joined(separator: ",") + "]"

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let c = WKWebViewConfiguration()
        c.websiteDataStore = .nonPersistent()
        c.defaultWebpagePreferences.allowsContentJavaScript = false
        c.dataDetectorTypes = []
        let v = WKWebView(frame: .zero, configuration: c)
        v.navigationDelegate = context.coordinator
        v.scrollView.isScrollEnabled = false
        v.isOpaque = false
        v.layer.cornerRadius = 10
        v.clipsToBounds = true
        context.coordinator.show(v, page)
        return v
    }

    func updateUIView(_ v: WKWebView, context: Context) {
        context.coordinator.parent = self
        if context.coordinator.shown != page { context.coordinator.show(v, page) }
    }

    /// whether the mail brings colours of its own (then it stays on white)
    var plain: Bool { html.range(of: #"(?i)bgcolor|background|[^-]color\s*:"#, options: .regularExpression, range: Self.bodyRange(html)) == nil }

    private static func bodyRange(_ h: String) -> Range<String.Index> {
        (h.range(of: "<body")?.lowerBound ?? h.startIndex)..<h.endIndex
    }

    /// the page as shown: in dark mode a plain mail gets light letters on no background of its own
    var page: String {
        guard dark && plain, let end = html.range(of: "</head>") else { return html }
        let css = "<style>html{color-scheme:dark}body{color:#e9ebf2;background:transparent}a[href]{color:#9aa8ff}"
            + "blockquote{border-left-color:#3b4357;color:#a3abbf}</style>"
        return html.replacingCharacters(in: end.lowerBound..<end.lowerBound, with: css)
    }

    @MainActor final class Coordinator: NSObject, WKNavigationDelegate {
        var parent: MailPageView
        var shown = ""
        init(_ parent: MailPageView) { self.parent = parent }

        /// the page only once the blocking rule is in place; without it nothing is shown (never loads from outside)
        func show(_ v: WKWebView, _ html: String) {
            shown = html
            v.backgroundColor = parent.dark && parent.plain ? .clear : .white
            Task { @MainActor in
                if MailPageView.rules == nil {
                    MailPageView.rules = try? await WKContentRuleListStore.default()
                        .compileContentRuleList(forIdentifier: "spark-mail-block", encodedContentRuleList: MailPageView.block)
                }
                guard let r = MailPageView.rules else { return }
                v.configuration.userContentController.removeAllContentRuleLists()
                v.configuration.userContentController.add(r)
                v.loadHTMLString(html, baseURL: nil)
            }
        }

        func webView(_ v: WKWebView, decidePolicyFor a: WKNavigationAction) async -> WKNavigationActionPolicy {
            if a.navigationType == .other, a.request.url?.absoluteString == "about:blank" {
                return .allow   // the page itself, from the string
            }
            if a.navigationType == .linkActivated, let u = a.request.url, ["http", "https", "mailto"].contains(u.scheme?.lowercased() ?? "") {
                parent.link(u)
            }
            return .cancel
        }

        func webView(_ v: WKWebView, didFinish navigation: WKNavigation!) {
            v.evaluateJavaScript("document.documentElement.scrollHeight") { h, _ in
                if let h = h as? CGFloat { self.parent.height = min(30000, max(48, h)) }
                else if let h = h as? Double { self.parent.height = min(30000, max(48, CGFloat(h))) }
            }
        }
    }
}

/// A new mail or an answer (Apple-Stil „3a“): own words go with „Senden“ after the Spark checked them and 10 s for
/// „Rückgängig“; text of the Spark (a suggestion, a rewrite, a draft of Für dich) keeps the preview sheet, only its
/// „Senden“ sends (senden.py).
struct MailDraft: Identifiable {
    var reply = ""
    var to = ""
    var subject = ""
    /// Weiterleiten (Mailclient Stufe C): the mail below the own words; its attachments only when wanted
    var forward = ""
    var folder = "INBOX"
    var files: [String] = []
    /// a text the form starts with (Für dich: the fixed draft of a cancelling mail, FuerDich.swift)
    var text = ""
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
    /// the text came from the Spark (a suggestion, a rewrite, a draft of Für dich): the preview sheet stays
    @State private var spark = false
    /// the checked mail waiting its 10 s for „Rückgängig“, and the seconds left
    @State private var pending: [String: Any]?
    @State private var left = 10
    @State private var waiter: Task<Void, Never>?
    /// Später senden (Dominik 2026-10-21 „4“): the time picked on its own sheet
    @State private var laterOpen = false
    @State private var laterAt = Date().addingTimeInterval(3600)
    private static let tones: [(String, LocalizedStringKey)] = [("kuerzer", "kürzer"), ("freundlicher", "freundlicher"),
                                                                ("foermlicher", "förmlicher"), ("uebersetzen", "auf Englisch")]

    var body: some View {
        NavigationStack {
            Form {
                if let p = pending {
                    Section {
                        Text(verbatim: String(localized: "Wird gesendet an ") + (p["to"] as? [String] ?? []).joined(separator: ", "))
                        Text(verbatim: String(localized: "in \(left) s")).font(.title2.weight(.semibold)).monospacedDigit()
                        Button("Rückgängig") { undo() }.font(.headline)
                        Button("Jetzt senden") { waiter?.cancel(); Task { await sendNow() } }.disabled(busy)
                    }
                } else if let p = preview {
                    Section {
                        LabeledContent("Von") { Text(verbatim: p["from"] as? String ?? "") }
                        if let v = p["server"] as? String, !v.isEmpty { LabeledContent("Über") { Text(verbatim: v) } }
                        LabeledContent("An") { Text(verbatim: (p["to"] as? [String] ?? []).joined(separator: ", ")) }
                        if let c = p["cc"] as? [String], !c.isEmpty { LabeledContent("Kopie") { Text(verbatim: c.joined(separator: ", ")) } }
                        LabeledContent("Betreff") { Text(verbatim: p["subject"] as? String ?? "") }
                        if let f = p["files"] as? [String], !f.isEmpty { LabeledContent("Anhänge") { Text(verbatim: f.prefix(20).joined(separator: ", ")) } }
                    } header: { Text("So geht die Mail raus") }
                    Section { Text(verbatim: p["text"] as? String ?? "") }
                    Section {
                        Button("Senden") { Task { await send() } }.disabled(busy)
                        Button("Später senden …") { laterOpen = true }.disabled(busy)
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
                                Text(ideasNote.map { SparkAPI.way($0) } ?? AttributedString(localized: "Vorschläge kommen …")).foregroundStyle(.secondary)
                            }
                            ForEach(Array(ideas.enumerated()), id: \.offset) { i, x in
                                Button {
                                    text = x.1
                                    picked = i
                                    spark = true
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
                        Text(spark ? LocalizedStringKey("Mit Text vom Spark: vor dem Senden kommt die Vorschau.")
                             : draft.forward.isEmpty ? LocalizedStringKey("Nach „Senden“ hast du 10 s für „Rückgängig“.")
                             : LocalizedStringKey("Deine Zeilen stehen über der weitergeleiteten Mail und dürfen leer bleiben. Nach „Senden“ hast du 10 s für „Rückgängig“."))
                    }
                    Section {
                        Button { Task { await go() } } label: { Label("Senden", systemImage: "paperplane.fill") }
                            .disabled(busy || (draft.forward.isEmpty && text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
                        if !spark {
                            Button { laterOpen = true } label: { Label("Später senden …", systemImage: "clock") }
                                .disabled(busy || (draft.forward.isEmpty && text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
                        }
                    }
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
            }
            .navigationTitle(!draft.reply.isEmpty ? Text("Antworten") : !draft.forward.isEmpty ? Text("Weiterleiten") : Text("Neue Mail"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Verwerfen") { dismiss() }.disabled(pending != nil) } }
            .onAppear { if to.isEmpty && subject.isEmpty { to = draft.to; subject = draft.subject; text = draft.text; spark = !draft.text.isEmpty } }
            .task { if !draft.reply.isEmpty && ideas.isEmpty { await suggest() } }
            .interactiveDismissDisabled(busy || pending != nil)
            .sheet(isPresented: $laterOpen) {
                NavigationStack {
                    Form {
                        DatePicker("Senden am", selection: $laterAt, in: Date().addingTimeInterval(120)...Date().addingTimeInterval(30 * 86400))
                        Button("Planen") { laterOpen = false; Task { await later() } }.disabled(busy)
                    }
                    .navigationTitle("Später senden")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { laterOpen = false } } }
                }
                .presentationDetents([.medium])
            }
        }
    }

    /// Später senden: checked like „Senden“ (the preview), then planned on the Spark; it can be taken back until then
    private func later() async {
        if preview == nil { await look() }
        guard let api = SparkAPI.current, let token = preview?["token"] as? String else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.call("POST", "api/profile/mail/send", body: ["token": token, "at": Int(laterAt.timeIntervalSince1970)], timeout: 60)
            dismiss()
        } catch {
            self.error = error.localizedDescription
            preview = nil
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
            if let t = d["text"] as? String, !t.isEmpty { text = String(t.prefix(20000)); spark = true }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// „Senden“: the Spark checks the mail (the same check as the preview); own words then wait 10 s for „Rückgängig“
    private func go() async {
        await look()
        guard let p = preview, !spark else { return }   // text of the Spark: the preview sheet, only its „Senden“ sends
        preview = nil
        pending = p
        left = 10
        waiter = Task {
            for i in stride(from: 10, to: 0, by: -1) {
                left = i
                try? await Task.sleep(for: .seconds(1))
                if Task.isCancelled { return }
            }
            await sendNow()
        }
    }

    private func undo() {
        waiter?.cancel()
        waiter = nil
        pending = nil   // nothing went out; the form keeps everything typed
    }

    private func sendNow() async {
        guard let api = SparkAPI.current, let token = pending?["token"] as? String else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.call("POST", "api/profile/mail/send", body: ["token": token], timeout: 120)
            pending = nil
            dismiss()
        } catch {
            self.error = error.localizedDescription
            pending = nil
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
