import Foundation

// Version 4 (speak, inbox, agenda, quiet, meeting, home, daily): the pieces without AppKit, so they can be checked
// on their own. Everything from the Spark is parsed defensively: odd values are dropped, never trusted.

// ------------------------------------------------------------------ plain text

enum PlainText {
    /// one line, control characters out, at most `max` characters
    static func line(_ raw: Any?, max: Int) -> String {
        guard let s = raw as? String else { return "" }
        let clean = String(s.unicodeScalars.map { u -> Character in
            u.properties.generalCategory == .control ? " " : Character(u)
        })
        return String(clean.trimmingCharacters(in: .whitespacesAndNewlines).prefix(max))
    }

    /// several lines kept, other control characters out, at most `max` characters
    static func block(_ raw: Any?, max: Int) -> String {
        guard let s = raw as? String else { return "" }
        let clean = String(s.unicodeScalars.map { u -> Character in
            (u.properties.generalCategory == .control && u != "\n" && u != "\t") ? " " : Character(u)
        })
        return String(clean.trimmingCharacters(in: .whitespacesAndNewlines).prefix(max))
    }
}

// ------------------------------------------------------------------ speak

enum SpeakText {
    static let max = 5000

    /// what goes to /api/desk/speak: trimmed, at most 5000 characters; nil when nothing is left
    static func prepare(_ raw: String) -> (text: String, cut: Bool)? {
        let t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        if t.count > max { return (String(t.prefix(max)), true) }
        return (t, false)
    }

    /// RIFF/WAVE header check: only a real WAV goes to the player
    static func looksLikeWav(_ d: Data) -> Bool {
        guard d.count > 44 else { return false }
        let b = [UInt8](d.prefix(12))
        return b[0] == 0x52 && b[1] == 0x49 && b[2] == 0x46 && b[3] == 0x46     // RIFF
            && b[8] == 0x57 && b[9] == 0x41 && b[10] == 0x56 && b[11] == 0x45   // WAVE
    }
}

// ------------------------------------------------------------------ inbox

struct InboxItem: Equatable {
    enum Kind: String {
        case text, link, file
    }

    let id: String
    let kind: Kind
    let text: String
    let name: String
    let size: Int?

    static let maxFile = 20 * 1024 * 1024

    /// poll "inbox", checked; the id must be safe for the query ?id=…
    static func list(_ raw: Any?) -> [InboxItem] {
        guard let arr = raw as? [Any] else { return [] }
        var out: [InboxItem] = []
        for item in arr.prefix(20) {
            guard let d = item as? [String: Any] else { continue }
            let id: String
            if let s = d["id"] as? String { id = s } else if let n = d["id"] as? NSNumber { id = n.stringValue } else { continue }
            guard ActAsk.validID(id), let k = d["kind"] as? String, let kind = Kind(rawValue: k) else { continue }
            let text = kind == .text ? PlainText.block(d["text"], max: 100_000) : PlainText.line(d["text"], max: 4000)
            let name = PlainText.line(d["name"], max: 255)
            let size = (d["size"] as? NSNumber)?.intValue
            if kind != .file && text.isEmpty { continue }
            out.append(InboxItem(id: id, kind: kind, text: text, name: name, size: size))
        }
        return out
    }

    /// a link that may be opened: only http and https with a host
    static func openable(_ s: String) -> URL? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count <= 2000, let u = URL(string: t), let scheme = u.scheme?.lowercased(),
              scheme == "http" || scheme == "https", let host = u.host, !host.isEmpty else { return nil }
        return u
    }
}

enum InboxName {
    /// a file name without path parts, control characters or a leading dot; never empty
    static func sanitize(_ raw: String) -> String {
        var s = raw.replacingOccurrences(of: "\\", with: "/")
        if let last = s.split(separator: "/").last { s = String(last) } else { s = "" }
        s = String(s.unicodeScalars.map { u -> Character in
            if u.properties.generalCategory == .control || u == ":" { return "_" }
            return Character(u)
        })
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasPrefix(".") { s.removeFirst() }
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.count > 120 {
            let ext = (s as NSString).pathExtension
            let keep = ext.isEmpty || ext.count > 10 ? 120 : 119 - ext.count
            s = String(s.prefix(keep)) + (ext.isEmpty || ext.count > 10 ? "" : "." + ext)
        }
        return s.isEmpty ? "datei" : s
    }

    /// "name.ext", or "name (2).ext", "name (3).ext" … — the first that `exists` says is free
    static func unique(_ name: String, exists: (String) -> Bool) -> String {
        guard exists(name) else { return name }
        let ns = name as NSString
        let ext = ns.pathExtension
        let stem = ext.isEmpty ? name : ns.deletingPathExtension
        for i in 2...9999 {
            let candidate = ext.isEmpty ? "\(stem) (\(i))" : "\(stem) (\(i)).\(ext)"
            if !exists(candidate) { return candidate }
        }
        return "\(stem) (\(UUID().uuidString.prefix(8)))" + (ext.isEmpty ? "" : ".\(ext)")
    }
}

// ------------------------------------------------------------------ dates (agenda, reminders, tasks)

enum IsoDate {
    /// "2026-10-11T14:00:00+02:00", with or without fractions, "…Z", or a plain day "2026-10-11" (local midnight)
    static func parse(_ raw: Any?) -> Date? {
        guard let s = raw as? String, !s.isEmpty, s.count <= 40 else { return nil }
        let full = ISO8601DateFormatter()
        full.formatOptions = [.withInternetDateTime]
        if let d = full.date(from: s) { return d }
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = frac.date(from: s) { return d }
        // without a zone: local time
        let local = DateFormatter()
        local.locale = Locale(identifier: "en_US_POSIX")
        local.timeZone = TimeZone.current
        for f in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd"] {
            local.dateFormat = f
            if let d = local.date(from: s) { return d }
        }
        return nil
    }

    /// "14:00", "morgen 9:00", "Mo 13.10. 9:00" (German, local time)
    static func short(_ d: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        let time = DateFormatter()
        time.locale = Locale(identifier: "de_DE")
        time.timeZone = calendar.timeZone
        time.dateFormat = "H:mm"
        let t = time.string(from: d)
        if calendar.isDate(d, inSameDayAs: now) { return t }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(d, inSameDayAs: tomorrow) {
            return "morgen " + t
        }
        let day = DateFormatter()
        day.locale = Locale(identifier: "de_DE")
        day.timeZone = calendar.timeZone
        day.dateFormat = "EEE d.M."
        return day.string(from: d).replacingOccurrences(of: ".,", with: ".") + " " + t
    }
}

// ------------------------------------------------------------------ agenda

struct AgendaEvent: Equatable, Identifiable {
    let start: Date
    let end: Date?
    let title: String
    let place: String
    /// the profile that shares this calendar ("" for an own one, Begleiter nachziehen 7a)
    var who = ""
    /// YYYY-MM-DD: a click opens the page Kalender on that day (#kal=…), "" = nothing to open
    var day = ""

    /// stable per event (start + title), for "once per event"
    var id: String {
        let t = Int(start.timeIntervalSince1970)
        var h: UInt64 = 1469598103934665603                  // FNV-1a over the title: no title text in the key
        for b in title.utf8 {
            h ^= UInt64(b)
            h = h &* 1099511628211
        }
        return "\(t)-\(String(h, radix: 16))"
    }
}

struct AgendaReminder: Equatable {
    let due: Date
    let text: String
}

struct Agenda: Equatable {
    var events: [AgendaEvent] = []
    var reminders: [AgendaReminder] = []

    static let leadMinutes = 10.0

    /// GET /api/desk/agenda, checked: at most 10 each, sorted by time
    init(_ d: [String: Any]) {
        events = (d["events"] as? [Any] ?? []).prefix(10).compactMap { x -> AgendaEvent? in
            guard let e = x as? [String: Any], let start = IsoDate.parse(e["start"]) else { return nil }
            let title = PlainText.line(e["title"], max: 200)
            let day = e["day"] as? String ?? ""
            return AgendaEvent(start: start, end: IsoDate.parse(e["end"]),
                               title: title.isEmpty ? "Termin" : title, place: PlainText.line(e["where"], max: 120),
                               who: PlainText.line(e["who"], max: 40), day: Agenda.isDay(day) ? day : "")
        }.sorted { $0.start < $1.start }
        reminders = (d["reminders"] as? [Any] ?? []).prefix(10).compactMap { x -> AgendaReminder? in
            guard let r = x as? [String: Any], let due = IsoDate.parse(r["due"]) else { return nil }
            let text = PlainText.line(r["text"], max: 300)
            return AgendaReminder(due: due, text: text.isEmpty ? "Erinnerung" : text)
        }.sorted { $0.due < $1.due }
    }

    init() {}

    /// "2026-10-21" and nothing else: the only thing a click puts into the panel's address (#kal=…)
    static func isDay(_ s: String) -> Bool {
        s.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil
    }

    /// one line per thing, the next ones first (events still running count too)
    struct Line: Equatable, Identifiable {
        let id: String
        let when: Date
        let isReminder: Bool
        let title: String
        let detail: String
        var who = ""
        var day = ""
    }

    func upcoming(now: Date, limit: Int = 5) -> [Line] {
        var out: [Line] = []
        for e in events where (e.end ?? e.start.addingTimeInterval(3600)) > now {
            out.append(Line(id: "e" + e.id, when: e.start, isReminder: false, title: e.title, detail: e.place, who: e.who, day: e.day))
        }
        for (i, r) in reminders.enumerated() where r.due > now.addingTimeInterval(-300) {
            out.append(Line(id: "r\(i)-\(Int(r.due.timeIntervalSince1970))", when: r.due, isReminder: true,
                            title: r.text, detail: ""))
        }
        return Array(out.sorted { $0.when < $1.when }.prefix(limit))
    }

    /// When to tell about each event: `.at(date)` 10 min before its start (in the future), `.now` when that moment
    /// has just passed but the event has not begun (the program started late), nothing for events already running.
    enum Alert: Equatable {
        case at(Date)
        case now
    }

    static func alert(for e: AgendaEvent, now: Date) -> Alert? {
        let at = e.start.addingTimeInterval(-leadMinutes * 60)
        if at > now { return .at(at) }
        if e.start > now { return .now }
        return nil
    }
}

enum Remind {
    static let defaultMinutes = 20

    static func minutes(_ m: Int) -> Int { min(max(m, 1), 1440) }
}

// ------------------------------------------------------------------ home

struct HomeButton: Equatable, Identifiable {
    let id: String
    let name: String
    let kind: String            // toggle | scene | script
    var state: String?          // on | off | nil

    static let kinds = ["toggle", "scene", "script"]

    /// config.home.buttons or GET /api/desk/home "buttons", checked
    static func list(_ raw: Any?) -> [HomeButton] {
        guard let arr = raw as? [Any] else { return [] }
        var out: [HomeButton] = []
        for x in arr.prefix(30) {
            guard let d = x as? [String: Any], let id = d["id"] as? String, !id.isEmpty, id.count <= 200,
                  !id.contains("\0") else { continue }
            let name = PlainText.line(d["name"], max: 60)
            let kindRaw = (d["kind"] as? String) ?? "toggle"
            let kind = kinds.contains(kindRaw) ? kindRaw : "toggle"
            if out.contains(where: { $0.id == id }) { continue }
            out.append(HomeButton(id: id, name: name.isEmpty ? id : name, kind: kind, state: state(d["state"])))
        }
        return out
    }

    static func state(_ raw: Any?) -> String? {
        guard let s = raw as? String else { return nil }
        return s == "on" || s == "off" ? s : nil
    }

    /// 403 whose detail asks for the code word
    static func wantsCode(_ detail: String) -> Bool {
        detail.hasPrefix("Codewort")
    }
}

// ------------------------------------------------------------------ meeting

struct MeetingTask: Equatable, Identifiable {
    let index: Int
    let text: String
    let due: Date?
    var id: Int { index }
}

/// a list the meeting's tasks may go onto (id, name, symbol); "Aufgaben" comes first from the Spark
struct MeetingList: Equatable, Identifiable, Hashable {
    let id: String
    let name: String
    let icon: String
}

struct MeetingResult: Equatable {
    let summary: String
    let tasks: [MeetingTask]
    let chars: Int
    /// empty: the lists are not allowed for the profile, only reminders
    let lists: [MeetingList]

    /// POST /api/desk/meeting/end, checked; the index is the position in the Spark's list (what "keep" sends back)
    init(_ d: [String: Any]) {
        summary = PlainText.block(d["summary"], max: 50_000)
        var list: [MeetingTask] = []
        for (i, x) in (d["tasks"] as? [Any] ?? []).prefix(50).enumerated() {
            guard let t = x as? [String: Any] else { continue }
            let text = PlainText.line(t["text"], max: 500)
            if text.isEmpty { continue }
            list.append(MeetingTask(index: i, text: text, due: IsoDate.parse(t["due"])))
        }
        tasks = list
        chars = (d["chars"] as? NSNumber)?.intValue ?? 0
        lists = (d["lists"] as? [Any] ?? []).prefix(30).compactMap { x -> MeetingList? in
            guard let l = x as? [String: Any], let id = l["id"] as? String, !id.isEmpty, id.count <= 20,
                  id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }) else { return nil }
            return MeetingList(id: id, name: PlainText.line(l["name"], max: 40), icon: PlainText.line(l["icon"], max: 4))
        }
    }
}

enum MeetingAudio {
    static let rate = 16000
    static let chunkSeconds = 30.0
    static let maxSeconds = 3 * 3600.0
    /// what a source may hold between two chunks (a late chunk must stay ≤ 60 s)
    static let bufferSeconds = 55.0

    /// Mixes two 16-bit mono streams (little endian) sample by sample, the shorter one padded with silence.
    /// Both at 0.8 so speech of both sides rarely clips; clipped to Int16.
    static func mix(_ a: Data, _ b: Data) -> Data {
        let na = a.count / 2
        let nb = b.count / 2
        let n = max(na, nb)
        guard n > 0 else { return Data() }
        if nb == 0 { return a.prefix(na * 2) }
        if na == 0 { return b.prefix(nb * 2) }
        var out = Data(count: n * 2)
        a.withUnsafeBytes { (pa: UnsafeRawBufferPointer) in
            b.withUnsafeBytes { (pb: UnsafeRawBufferPointer) in
                out.withUnsafeMutableBytes { (po: UnsafeMutableRawBufferPointer) in
                    for i in 0..<n {
                        let x = i < na ? Int(Int16(littleEndian: pa.loadUnaligned(fromByteOffset: i * 2, as: Int16.self))) : 0
                        let y = i < nb ? Int(Int16(littleEndian: pb.loadUnaligned(fromByteOffset: i * 2, as: Int16.self))) : 0
                        let m = (x * 8 + y * 8) / 10
                        let c = Int16(clamping: m)
                        po.storeBytes(of: c.littleEndian, toByteOffset: i * 2, as: Int16.self)
                    }
                }
            }
        }
        return out
    }

    /// "03:12" or "1:03:12"
    static func clock(_ seconds: Int) -> String {
        let s = max(0, seconds)
        if s >= 3600 { return String(format: "%d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60) }
        return String(format: "%02d:%02d", s / 60, s % 60)
    }
}

// ------------------------------------------------------------------ daily

enum DailyPlan {
    static let morningDefault = 6 * 60          // 06:00
    static let eveningDefault = 17 * 60 + 30    // 17:30

    static func minuteOfDay(_ d: Date, calendar: Calendar = .current) -> Int {
        let c = calendar.dateComponents([.hour, .minute], from: d)
        return (c.hour ?? 0) * 60 + (c.minute ?? 0)
    }

    /// once a day, from `minutes` on: not yet today and late enough
    static func due(now: Date, minutes: Int, lastDay: String?, calendar: Calendar = .current) -> Bool {
        let today = FolderLedger.dayString(now)
        guard lastDay != today else { return false }
        return minuteOfDay(now, calendar: calendar) >= minutes
    }

    /// "06:00"
    static func label(_ minutes: Int) -> String {
        let m = min(max(minutes, 0), 24 * 60 - 1)
        return String(format: "%02d:%02d", m / 60, m % 60)
    }
}

// ------------------------------------------------------------------ quiet

enum QuietLogic {
    struct Rect: Equatable {
        let x: Double, y: Double, w: Double, h: Double
    }

    /// a window of the front app that covers a whole display (full screen, a running presentation)
    static func coversDisplay(_ windows: [Rect], displays: [Rect], tolerance: Double = 2) -> Bool {
        for w in windows where w.w >= 200 && w.h >= 200 {
            for d in displays where abs(w.x - d.x) <= tolerance && abs(w.y - d.y) <= tolerance
                && w.w >= d.w - tolerance && w.h >= d.h - tolerance {
                return true
            }
        }
        return false
    }

    /// "call" wins over "present" (a call while presenting is still a call)
    static func why(mic: Bool, camera: Bool, fullScreen: Bool) -> String? {
        if mic || camera { return "call" }
        if fullScreen { return "present" }
        return nil
    }

    /// apps that are full screen often without anything to hide (the desktop, the login window)
    static let ignoredBundles: Set<String> = ["com.apple.finder", "com.apple.loginwindow", "com.apple.dock",
                                              "com.apple.ScreenSaver.Engine", "de.db9979.spark.begleiter"]
}

// ------------------------------------------------------------------ new config fields

struct V4Config: Equatable {
    /// config.meeting.remarkable
    var meetingRemarkable = false
    /// config.home.buttons
    var homeButtons: [HomeButton] = []

    init() {}

    init(_ d: [String: Any]) {
        meetingRemarkable = ((d["meeting"] as? [String: Any])?["remarkable"] as? Bool) ?? false
        homeButtons = HomeButton.list((d["home"] as? [String: Any])?["buttons"])
    }
}

// ------------------------------------------------------------------ "In 20 Min erinnern" on notes

extension NoteActions {
    /// the note buttons plus "remind" (part agenda)
    static let withRemind = known + ["remind"]

    /// one category per combination, "remind" last ("note.reply.open.remind"); without it the same ids as before
    static func category4(_ actions: [String]) -> String? {
        let a = withRemind.filter { actions.contains($0) }
        return a.isEmpty ? nil : "note." + a.joined(separator: ".")
    }

    /// a note about an important new mail (tag "mail-new", part post): Antwort entwerfen, Gelesen (Mails ordnen), Ansehen
    static let mailTag = "mail-new"
    static let mail = ["draft", "read", "open"]
    /// what "Antwort entwerfen" puts into the field of Frag Spark (sent only when the person presses Enter)
    static let draftQuestion = "Entwirf eine kurze Antwort auf diese Mail. Nicht senden."

    /// a note with a confirmation code (tag "mailcode", mailcode.py): only „Code kopieren“, the code is the first word
    static let codeTag = "mailcode"
    static let code = ["copy"]
    static let codeCategory = "code.copy"

    /// the code of such a note: its first word when it looks like one (4 to 8 capitals or digits), else nil
    static func codeOf(_ body: String) -> String? {
        guard let first = body.split(separator: " ").first.map(String.init),
              first.range(of: "^[A-Z0-9]{4,8}$", options: .regularExpression) != nil else { return nil }
        return first
    }

    static func parseCode(_ raw: Any?) -> [String] {
        let given = (raw as? [Any] ?? []).compactMap { $0 as? String }
        return code.filter { given.contains($0) }
    }

    static func parseMail(_ raw: Any?) -> [String] {
        let given = (raw as? [Any] ?? []).compactMap { $0 as? String }
        return mail.filter { given.contains($0) }
    }

    static func mailCategory(_ actions: [String]) -> String? {
        let a = mail.filter { actions.contains($0) }
        return a.isEmpty ? nil : "mail." + a.joined(separator: ".")
    }

    static var mailCombinations: [[String]] {
        (1..<(1 << mail.count)).map { mask in mail.enumerated().filter { mask & (1 << $0.offset) != 0 }.map { $0.element } }
    }

    static var allCombinations4: [[String]] {
        var out: [[String]] = []
        for mask in 1..<(1 << withRemind.count) {
            out.append(withRemind.enumerated().filter { mask & (1 << $0.offset) != 0 }.map { $0.element })
        }
        return out
    }
}

// ------------------------------------------------------------------ act: the installed programs for the panel

enum InstalledList {
    static let maxEntries = 600
    static let maxName = 40
    static let maxPath = 300
    static let refreshSeconds: TimeInterval = 24 * 3600

    /// POST /api/desk/apps "apps": names cleaned and cut, paths ≤ 300 (longer ones left out), deduped by path and
    /// by name (the first of a name wins: the caller lists /Applications before the others), sorted by name.
    static func normalize(_ raw: [(name: String, path: String)]) -> [[String: String]] {
        var byPath: Set<String> = []
        var byName: Set<String> = []
        var out: [(name: String, path: String)] = []
        for item in raw {
            let path = item.path
            guard !path.isEmpty, path.count <= maxPath, !path.contains("\0"), path.hasPrefix("/") else { continue }
            var name = PlainText.line(item.name, max: 200)
            if name.lowercased().hasSuffix(".app") { name = String(name.dropLast(4)) }
            name = String(name.trimmingCharacters(in: .whitespaces).prefix(maxName))
            guard !name.isEmpty else { continue }
            let key = name.lowercased()
            guard !byPath.contains(path), !byName.contains(key) else { continue }
            byPath.insert(path)
            byName.insert(key)
            out.append((name, path))
        }
        out.sort { a, b in
            let c = a.name.localizedCaseInsensitiveCompare(b.name)
            return c == .orderedSame ? a.path < b.path : c == .orderedAscending
        }
        return out.prefix(maxEntries).map { ["name": $0.name, "path": $0.path] }
    }

    /// whether it is time to send again (once a day, or when the list changed)
    static func due(lastSent: Date?, lastHash: String?, hash: String, now: Date) -> Bool {
        guard let lastSent, lastHash == hash else { return true }
        return now.timeIntervalSince(lastSent) >= refreshSeconds
    }
}

// ------------------------------------------------------------------ the ask window speaks (part speak)

enum AskSpeak {
    static let key = "ask.speak"
    static let modes: [(id: String, title: String)] = [("always", "immer"), ("voice", "nur bei gesprochenen Fragen"),
                                                       ("never", "nie")]

    static var ids: [String] { modes.map { $0.id } }

    static func title(_ raw: String?) -> String {
        let m = mode(raw)
        return modes.first { $0.id == m }?.title ?? ""
    }

    static func mode(_ raw: String?) -> String {
        guard let raw, modes.contains(where: { $0.id == raw }) else { return "voice" }
        return raw
    }

    /// read the answer aloud? (only with part speak on)
    static func wanted(mode raw: String?, spoken: Bool, speakOn: Bool) -> Bool {
        guard speakOn else { return false }
        switch mode(raw) {
        case "always": return true
        case "never": return false
        default: return spoken
        }
    }
}
