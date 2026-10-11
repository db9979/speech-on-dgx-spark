import Foundation

// Version 3 ("deeper integration"): the pieces without AppKit, so they can be checked on their own.

// ------------------------------------------------------------------ context: the front app's category

/// Only a category leaves the Mac ("outlook", "browser", …), never a name or a window title.
enum AppCategory {
    static let all = ["outlook", "mail", "word", "excel", "powerpoint", "pages", "browser", "teams", "chat", "code", "other"]

    private static let exact: [String: String] = [
        "com.microsoft.outlook": "outlook",
        "com.apple.mail": "mail",
        "com.microsoft.word": "word",
        "com.microsoft.excel": "excel",
        "com.microsoft.powerpoint": "powerpoint",
        "com.apple.iwork.pages": "pages",
        "com.apple.safari": "browser",
        "com.apple.safaritechnologypreview": "browser",
        "org.mozilla.firefox": "browser",
        "org.mozilla.firefoxdeveloperedition": "browser",
        "org.mozilla.nightly": "browser",
        "company.thebrowser.browser": "browser",          // Arc
        "com.operasoftware.opera": "browser",
        "com.vivaldi.vivaldi": "browser",
        "com.microsoft.teams": "teams",
        "com.microsoft.teams2": "teams",
        "com.tinyspeck.slackmacgap": "chat",
        "com.hnc.discord": "chat",
        "net.whatsapp.whatsapp": "chat",
        "desktop.whatsapp": "chat",
        "ru.keepcoder.telegram": "chat",
        "org.telegram.desktop": "chat",
        "org.whispersystems.signal-desktop": "chat",
        "com.apple.mobilesms": "chat",                     // Nachrichten
        "com.apple.dt.xcode": "code",
        "com.microsoft.vscode": "code",
        "com.microsoft.vscodeinsiders": "code",
        "com.vscodium": "code",
        "com.todesktop.230313mzl4w4u92": "code",           // Cursor
        "dev.zed.zed": "code",
        "com.sublimetext.4": "code",
    ]

    private static let prefixes: [(String, String)] = [
        ("com.google.chrome", "browser"),                  // Chrome, Chrome Beta/Canary
        ("com.microsoft.edgemac", "browser"),              // Edge and its channels
        ("com.brave.browser", "browser"),
        ("com.jetbrains.", "code"),                        // IntelliJ, PyCharm, …
    ]

    static func of(bundleID: String?) -> String {
        guard let raw = bundleID?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !raw.isEmpty else {
            return "other"
        }
        if let c = exact[raw] { return c }
        for (p, c) in prefixes where raw.hasPrefix(p) { return c }
        return "other"
    }
}

// ------------------------------------------------------------------ act: what the Spark may do on this Mac

/// One entry of config.act.apps: the name the Spark uses and what this Mac starts.
struct ActApp: Equatable {
    let name: String
    let path: String

    /// config.act.apps, checked: only plain names and an absolute ".app" path or a bundle id.
    static func list(_ raw: Any?) -> [ActApp] {
        guard let arr = raw as? [Any] else { return [] }
        var out: [ActApp] = []
        for item in arr.prefix(50) {
            guard let d = item as? [String: Any],
                  let n = d["name"] as? String, let p = d["path"] as? String else { continue }
            let name = n.trimmingCharacters(in: .whitespacesAndNewlines)
            let path = p.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name.count <= 80, !path.isEmpty, path.count <= 1024,
                  !path.contains("\0"), !name.contains("\0") else { continue }
            out.append(ActApp(name: name, path: path))
        }
        return out
    }

    enum Target: Equatable {
        case bundle(String)     // "com.apple.Safari"
        case path(String)       // "/Applications/Safari.app"
        case name(String)       // "Safari" -> /Applications/Safari.app, /System/Applications/…
    }

    /// what `path` means; nil when it is none of the three (then the app is refused)
    var target: Target? {
        if path.hasPrefix("/") || path.hasPrefix("~/") {
            let p = path.hasPrefix("~/") ? NSHomeDirectory() + String(path.dropFirst(1)) : path
            let std = (p as NSString).standardizingPath
            let trimmed = std.hasSuffix("/") ? String(std.dropLast()) : std
            guard trimmed.lowercased().hasSuffix(".app"), !trimmed.contains("/../") else { return nil }
            return .path(trimmed)
        }
        let bundleChars = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
        if path.contains("."), !path.hasSuffix(".app"), path.split(separator: ".").count >= 2,
           path.unicodeScalars.allSatisfy({ bundleChars.contains($0) }) {
            return .bundle(path)
        }
        var name = path
        if name.lowercased().hasSuffix(".app") { name = String(name.dropLast(4)) }
        guard !name.isEmpty, !name.contains("/"), !name.contains(":"), name != ".", name != ".." else { return nil }
        return .name(name)
    }
}

/// One wish of the Spark from the poll ("asks").
struct ActAsk: Equatable {
    let id: String
    let action: String
    let arg: String
    let text: String

    /// poll "asks", checked; the id must be safe to put into the path /api/desk/act/{id}
    static func list(_ raw: Any?) -> [ActAsk] {
        guard let arr = raw as? [Any] else { return [] }
        var out: [ActAsk] = []
        for item in arr.prefix(20) {
            guard let d = item as? [String: Any] else { continue }
            let id: String
            if let s = d["id"] as? String { id = s } else if let n = d["id"] as? NSNumber { id = n.stringValue } else { continue }
            guard validID(id), let action = d["action"] as? String else { continue }
            let arg = (d["arg"] as? String) ?? ""
            let text = (d["text"] as? String) ?? ""
            out.append(ActAsk(id: id, action: action, arg: String(arg.prefix(5000)), text: String(text.prefix(500))))
        }
        return out
    }

    static func validID(_ id: String) -> Bool {
        let ok = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        return !id.isEmpty && id.count <= 64 && id.unicodeScalars.allSatisfy { ok.contains($0) }
    }
}

/// What this Mac will actually do for an ask; everything else is refused.
enum ActPlan: Equatable {
    case url(URL)
    case app(ActApp)
    case media(String)      // play | pause | next | previous
    case volume(String)     // up | down | mute
    case lock
    case show(String)
    case refuse(String)

    static func make(_ ask: ActAsk, apps: [ActApp]) -> ActPlan {
        let arg = ask.arg.trimmingCharacters(in: .whitespacesAndNewlines)
        switch ask.action {
        case "url":
            guard let u = URL(string: arg), let scheme = u.scheme?.lowercased(), scheme == "http" || scheme == "https",
                  let host = u.host, !host.isEmpty, arg.count <= 2000 else {
                return .refuse("Nur http- und https-Adressen.")
            }
            return .url(u)
        case "app":
            guard let a = apps.first(where: { $0.name == arg })
                    ?? apps.first(where: { $0.name.lowercased() == arg.lowercased() }) else {
                return .refuse("Dieses Programm steht nicht in der Liste im Panel.")
            }
            guard a.target != nil else { return .refuse("Der Eintrag im Panel ist kein Programm.") }
            return .app(a)
        case "media":
            let a = arg.lowercased()
            return ["play", "pause", "next", "previous"].contains(a) ? .media(a) : .refuse("Unbekannter Medienbefehl.")
        case "volume":
            let a = arg.lowercased()
            return ["up", "down", "mute"].contains(a) ? .volume(a) : .refuse("Unbekannter Lautstärkebefehl.")
        case "lock":
            return .lock
        case "show":
            let t = ask.arg.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? .refuse("Kein Text zum Zeigen.") : .show(t)
        default:
            return .refuse("Diese Aktion kann der Begleiter nicht.")
        }
    }
}

/// ids of asks already answered (so the same id never runs twice), the newest few hundred
struct SeenIDs {
    private(set) var list: [String]
    let limit: Int

    init(_ list: [String], limit: Int = 300) {
        self.list = Array(list.suffix(limit))
        self.limit = limit
    }

    func contains(_ id: String) -> Bool { list.contains(id) }

    mutating func add(_ id: String) {
        guard !list.contains(id) else { return }
        list.append(id)
        if list.count > limit { list.removeFirst(list.count - limit) }
    }
}

// ------------------------------------------------------------------ actions on notes

enum NoteActions {
    static let known = ["reply", "later", "open"]

    /// the note's "actions", in a fixed order, unknown ones dropped
    static func parse(_ raw: Any?) -> [String] {
        let given = (raw as? [Any] ?? []).compactMap { $0 as? String }
        return known.filter { given.contains($0) }
    }

    /// one notification category per combination ("note.reply.open")
    static func category(_ actions: [String]) -> String? {
        let a = known.filter { actions.contains($0) }
        return a.isEmpty ? nil : "note." + a.joined(separator: ".")
    }

    static var allCombinations: [[String]] {
        var out: [[String]] = []
        for mask in 1..<(1 << known.count) {
            out.append(known.enumerated().filter { mask & (1 << $0.offset) != 0 }.map { $0.element })
        }
        return out
    }
}

// ------------------------------------------------------------------ files

enum FileKinds {
    static let maxBytes = 20 * 1024 * 1024
    static let types: [String: String] = [
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "odt": "application/vnd.oasis.opendocument.text",
        "txt": "text/plain",
        "md": "text/markdown",
        "markdown": "text/markdown",
        "eml": "message/rfc822",
        "html": "text/html",
        "htm": "text/html",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "heic": "image/heic",
    ]

    static func mime(for name: String) -> String? {
        let ext = (name as NSString).pathExtension.lowercased()
        return types[ext]
    }

    /// hidden, temporary and half-written files are never sent
    static func skip(_ name: String) -> Bool {
        let l = name.lowercased()
        if name.hasPrefix(".") || name.hasPrefix("~$") || name.hasPrefix("~") || name.hasPrefix("#") { return true }
        if name == "Icon\r" { return true }
        for s in [".tmp", ".temp", ".part", ".partial", ".crdownload", ".download", ".swp", ".lock", "~", ".icloud"]
        where l.hasSuffix(s) { return true }
        return false
    }

    /// the file name for the multipart header: no quotes, no line breaks, not empty
    static func safeName(_ name: String) -> String {
        var s = String(name.unicodeScalars.map { u -> Character in
            if u == "\"" || u == "\\" || u.properties.generalCategory == .control { return "_" }
            return Character(u)
        })
        if s.count > 120 {
            let ext = (s as NSString).pathExtension
            s = String(s.prefix(100)) + (ext.isEmpty ? "" : "." + ext)
        }
        return s.isEmpty ? "datei" : s
    }

    static let whats = ["zusammenfassen", "uebersetzen", "erklaeren", "wissen"]

    static func title(_ what: String) -> String {
        switch what {
        case "zusammenfassen": return "Zusammenfassen"
        case "uebersetzen": return "Übersetzen"
        case "erklaeren": return "Erklären"
        case "wissen": return "Ins Wissen übernehmen"
        default: return what
        }
    }
}

// ------------------------------------------------------------------ folder: what was sent already

/// The local list path -> size + mtime + sha256 of the files already in the Wissen, and the count of today.
struct FolderLedger: Codable, Equatable {
    struct Entry: Codable, Equatable {
        var size: Int
        var mtime: Double
        var sha256: String
    }

    var files: [String: Entry] = [:]
    var day = ""
    var countToday = 0

    static let perDay = 50

    static func dayString(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone.current
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }

    /// starts a new day's count when the date changed
    mutating func roll(_ now: Date) {
        let d = Self.dayString(now)
        if d != day {
            day = d
            countToday = 0
        }
    }

    var left: Int { max(0, Self.perDay - countToday) }

    /// unchanged by size and mtime: nothing to do (the sha256 is computed only for the others)
    func unchanged(_ path: String, size: Int, mtime: Double) -> Bool {
        guard let e = files[path] else { return false }
        return e.size == size && abs(e.mtime - mtime) < 0.001
    }

    /// same content as sent before (only touched): remember the new mtime, send nothing
    mutating func sameContent(_ path: String, size: Int, mtime: Double, sha256: String) -> Bool {
        guard let e = files[path], e.sha256 == sha256, e.size == size else { return false }
        files[path] = Entry(size: size, mtime: mtime, sha256: sha256)
        return true
    }

    mutating func done(_ path: String, size: Int, mtime: Double, sha256: String, counts: Bool) {
        files[path] = Entry(size: size, mtime: mtime, sha256: sha256)
        if counts { countToday += 1 }
    }

    /// files that no longer exist leave the list
    mutating func prune(existing: Set<String>) {
        files = files.filter { existing.contains($0.key) }
    }
}

/// "Quiet for 10 s": a file is taken when its size and mtime were the same in the previous scan and its mtime is
/// at least `quiet` seconds old.
struct QuietCheck {
    var seen: [String: (size: Int, mtime: Double)] = [:]
    let quiet: Double

    init(quiet: Double = 10) {
        self.quiet = quiet
    }

    mutating func ready(_ path: String, size: Int, mtime: Double, now: Double) -> Bool {
        let before = seen[path]
        seen[path] = (size, mtime)
        guard let b = before, b.size == size, abs(b.mtime - mtime) < 0.001 else { return false }
        return now - mtime >= quiet
    }

    mutating func forget(except existing: Set<String>) {
        seen = seen.filter { existing.contains($0.key) }
    }
}

// ------------------------------------------------------------------ screen: picture size

enum ScreenShot {
    static let maxSide = 2000
    static let maxBytes = 6 * 1024 * 1024
    static let maxQuestion = 500
    static let whats: [(id: String, title: String)] = [("erklaeren", "Erklären"), ("text", "Text herauslesen"),
                                                        ("uebersetzen", "Übersetzen")]

    /// the pixel size with the long side at most `maxSide` (never enlarged)
    static func fit(width: Int, height: Int, maxSide: Int = ScreenShot.maxSide) -> (width: Int, height: Int) {
        guard width > 0, height > 0 else { return (0, 0) }
        let long = max(width, height)
        guard long > maxSide else { return (width, height) }
        let f = Double(maxSide) / Double(long)
        return (max(1, Int((Double(width) * f).rounded())), max(1, Int((Double(height) * f).rounded())))
    }
}

// ------------------------------------------------------------------ wake: the level gate

/// Cuts speech out of the microphone's stream (16 kHz, mono, Int16): a frame of 20 ms counts as loud when its RMS
/// is above max(0.02, noise × 3); ≥ 80 ms loud starts a piece (with 0.4 s before it), 0.6 s quiet or the maximum
/// length ends it. `waitLimit` (seconds without speech) gives up (for the question after the wake word).
final class LevelGate {
    enum Event: Equatable {
        case piece(Data)
        case timeout
    }

    static let rate = 16000
    static let frame = 320                       // 20 ms

    let maxSamples: Int
    let preRollSamples: Int
    let pauseFrames: Int
    let startFrames: Int
    let waitFrames: Int?

    private(set) var noise = 0.01
    private(set) var capturing = false
    private var pending: [Int16] = []
    private var preRoll: [Int16] = []
    private var piece: [Int16] = []
    private var loudRun = 0
    private var quietRun = 0
    private var waited = 0

    init(maxSeconds: Double, preRoll: Double = 0.4, pause: Double = 0.6, minLoud: Double = 0.08,
         waitLimit: Double? = nil) {
        maxSamples = Int(maxSeconds * Double(Self.rate))
        preRollSamples = Int(preRoll * Double(Self.rate))
        pauseFrames = Int((pause * 1000 / 20).rounded())
        startFrames = max(1, Int((minLoud * 1000 / 20).rounded()))
        waitFrames = waitLimit.map { Int($0 * 1000 / 20) }
    }

    var threshold: Double { max(0.02, noise * 3) }

    static func rms(_ s: ArraySlice<Int16>) -> Double {
        guard !s.isEmpty else { return 0 }
        var sum = 0.0
        for v in s {
            let x = Double(v) / 32768
            sum += x * x
        }
        return (sum / Double(s.count)).squareRoot()
    }

    func reset() {
        capturing = false
        pending = []
        preRoll = []
        piece = []
        loudRun = 0
        quietRun = 0
        waited = 0
    }

    func feed(_ samples: [Int16]) -> [Event] {
        pending.append(contentsOf: samples)
        var out: [Event] = []
        var start = 0
        while pending.count - start >= Self.frame {
            let f = pending[start..<(start + Self.frame)]
            start += Self.frame
            if let e = step(f) {
                out.append(e)
                if e == .timeout { return out }        // reset() emptied everything
            }
        }
        pending.removeFirst(start)
        return out
    }

    private func step(_ f: ArraySlice<Int16>) -> Event? {
        let level = Self.rms(f)
        let loud = level > threshold
        if !capturing {
            preRoll.append(contentsOf: f)
            if preRoll.count > preRollSamples { preRoll.removeFirst(preRoll.count - preRollSamples) }
            if loud {
                loudRun += 1
                if loudRun >= startFrames {
                    capturing = true
                    piece = preRoll
                    preRoll = []
                    quietRun = 0
                    loudRun = 0
                    waited = 0
                }
            } else {
                loudRun = 0
                noise = noise * 0.95 + level * 0.05
                waited += 1
                if let w = waitFrames, waited >= w {
                    reset()
                    return .timeout
                }
            }
            return nil
        }
        piece.append(contentsOf: f)
        quietRun = loud ? 0 : quietRun + 1
        if quietRun >= pauseFrames || piece.count >= maxSamples {
            let samples = Array(piece.prefix(maxSamples))
            capturing = false
            piece = []
            quietRun = 0
            var d = Data(capacity: samples.count * 2)
            for v in samples {
                withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) }
            }
            return .piece(d)
        }
        return nil
    }
}

/// config.wake.word and the other new config parts, parsed defensively
enum WakeWord {
    static func parse(_ raw: Any?) -> String {
        guard let d = raw as? [String: Any], let w = d["word"] as? String else { return "Hey Spark" }
        let t = w.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? "Hey Spark" : String(t.prefix(40))
    }
}
