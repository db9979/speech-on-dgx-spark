import AppKit
import CryptoKit

/// Part "folder": a local folder (default ~/Spark-Wissen) is looked at every 15 s; new or changed files go to the
/// Wissen (POST /api/desk/file what=wissen) once they were quiet for 10 s. What was sent is remembered locally
/// (path → size + mtime + SHA-256) in Application Support/Spark Begleiter; at most 50 files a day.
/// Folders left out in the panel (config.auslassen, LeftOut) are not looked into; what was sent from them is
/// forgotten, so letting them in again sends their files anew. The sub folder names go to POST /api/desk/ordner
/// (names only) so the panel can show them as a tree.
@MainActor
final class FolderWatch: ObservableObject {
    static let shared = FolderWatch()
    static let pathKey = "folder.path"
    static let interval: TimeInterval = 15
    static let maxFilesPerScan = 2000
    /// the most sub folder names sent to the panel (auslassen.MAX_PC_DIRS)
    static let maxDirs = 2000

    @Published private(set) var active = false
    /// the last thing worth saying ("3 Dateien ins Wissen übernommen.", "Für heute …")
    @Published private(set) var lastText = ""
    @Published private(set) var path: URL

    private var timer: Timer?
    private var scanning = false
    private var ledger = FolderLedger()
    private var quiet = QuietCheck()
    private var loaded = false
    private var reportedDirs: [String]?
    private var reportedAt = Date.distantPast

    init() {
        if let s = UserDefaults.standard.string(forKey: Self.pathKey), s.hasPrefix("/") {
            path = URL(fileURLWithPath: s, isDirectory: true)
        } else {
            path = Self.defaultPath
        }
    }

    static var defaultPath: URL {
        URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).appendingPathComponent("Spark-Wissen", isDirectory: true)
    }

    nonisolated static var ledgerFile: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Spark Begleiter", isDirectory: true).appendingPathComponent("wissen-ordner.json")
    }

    // ------------------------------------------------------------------ on / off, the folder

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            loadLedger()
            ensureFolder()
            timer?.invalidate()
            let t = Timer(timeInterval: Self.interval, repeats: true) { _ in
                Task { @MainActor in await FolderWatch.shared.scan() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            Task { await scan() }
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            quiet = QuietCheck()
        }
    }

    /// a new folder from the settings window
    func setPath(_ url: URL) {
        path = url.standardizedFileURL
        UserDefaults.standard.set(path.path, forKey: Self.pathKey)
        quiet = QuietCheck()
        lastText = ""
        if active {
            ensureFolder()
            Task { await scan() }
        }
    }

    func chooseFolder() {
        NSApp.activate(ignoringOtherApps: true)
        let p = NSOpenPanel()
        p.canChooseDirectories = true
        p.canChooseFiles = false
        p.canCreateDirectories = true
        p.allowsMultipleSelection = false
        p.prompt = "Diesen Ordner beobachten"
        p.directoryURL = path
        if p.runModal() == .OK, let u = p.url {
            setPath(u)
        }
    }

    func reveal() {
        ensureFolder()
        NSWorkspace.shared.activateFileViewerSelecting([path])
    }

    private func ensureFolder() {
        let fm = FileManager.default
        var dir: ObjCBool = false
        if !fm.fileExists(atPath: path.path, isDirectory: &dir) {
            try? fm.createDirectory(at: path, withIntermediateDirectories: true)
        }
    }

    // ------------------------------------------------------------------ the list

    private func loadLedger() {
        guard !loaded else { return }
        loaded = true
        if let d = try? Data(contentsOf: Self.ledgerFile), let l = try? JSONDecoder().decode(FolderLedger.self, from: d) {
            ledger = l
        }
        ledger.needPlaces()
    }

    private func saveLedger() {
        let f = Self.ledgerFile
        try? FileManager.default.createDirectory(at: f.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let d = try? JSONEncoder().encode(ledger) {
            try? d.write(to: f, options: [.atomic])
        }
    }

    // ------------------------------------------------------------------ the scan

    struct Seen {
        let path: String
        let size: Int
        let mtime: Double
        /// the sub folder it lies in ("a/b", "" = right in the watched folder)
        var folder: String = ""
    }

    /// regular files in the folder (and below), hidden and temporary ones and left-out folders left out; and the
    /// sub folders ("a/b", left-out ones too, but not what lies below them)
    nonisolated static func list(_ root: URL, leftOut: LeftOut) -> (files: [Seen], dirs: [String]) {
        let keys: [URLResourceKey] = [.isRegularFileKey, .isDirectoryKey, .isPackageKey, .fileSizeKey,
                                      .contentModificationDateKey, .isHiddenKey]
        guard let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: keys,
                                                     options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return ([], []) }
        var out: [Seen] = []
        var dirs: [String] = []
        for case let u as URL in e {
            if out.count >= maxFilesPerScan { break }
            let name = u.lastPathComponent
            guard let v = try? u.resourceValues(forKeys: Set(keys)) else { continue }
            // the path below the watched folder, composed like the panel writes names (macOS keeps them decomposed)
            let rel = u.pathComponents.suffix(e.level).map { $0.precomposedStringWithCanonicalMapping }
            if v.isDirectory == true && v.isPackage != true {
                let p = rel.joined(separator: "/")
                if v.isHidden == true || leftOut.covers(p) {
                    e.skipDescendants()
                }
                if v.isHidden != true && dirs.count < maxDirs { dirs.append(p) }
                continue
            }
            if FileKinds.skip(name) || v.isHidden == true {
                continue
            }
            guard v.isRegularFile == true, let size = v.fileSize, size > 0, size <= FileKinds.maxBytes,
                  FileKinds.mime(for: name) != nil,
                  let m = v.contentModificationDate else { continue }
            out.append(Seen(path: u.path, size: size, mtime: m.timeIntervalSince1970,
                            folder: rel.dropLast().joined(separator: "/")))
        }
        return (out, dirs)
    }

    nonisolated static func sha256(_ path: String) -> String? {
        guard let h = FileHandle(forReadingAtPath: path) else { return nil }
        defer { try? h.close() }
        var hasher = SHA256()
        while true {
            // read(upToCount:) answers nil at the end of the file (not empty Data): that is the end, only
            // a thrown error is a failure
            let piece: Data?
            do { piece = try h.read(upToCount: 1 << 20) } catch { return nil }
            guard let chunk = piece, !chunk.isEmpty else { break }
            hasher.update(data: chunk)
        }
        return UpdateCheck.hex(Array(hasher.finalize()))
    }

    func scan() async {
        guard active, !scanning, let client = AppModel.shared.client else { return }
        scanning = true
        defer { scanning = false }
        let root = path
        let leftOut = AppModel.shared.config?.leftOut ?? LeftOut()
        let (files, dirs) = await Task.detached(priority: .utility) { Self.list(root, leftOut: leftOut) }.value
        let now = Date()
        await report(dirs, client: client, now: now)
        ledger.roll(now)
        let existing = Set(files.map { $0.path })
        quiet.forget(except: existing)
        var changed = false
        var sent = 0
        var problem = ""
        for f in files {
            guard active else { break }
            guard quiet.ready(f.path, size: f.size, mtime: f.mtime, now: now.timeIntervalSince1970),
                  !ledger.unchanged(f.path, size: f.size, mtime: f.mtime) else { continue }
            let path = f.path
            guard let sha = await Task.detached(priority: .utility, operation: { Self.sha256(path) }).value else { continue }
            if ledger.sameContent(f.path, size: f.size, mtime: f.mtime, sha256: sha) {
                changed = true
                continue
            }
            let again = ledger.resend(f.path, sha256: sha)
            guard again || ledger.left > 0 else {
                problem = "Für heute sind \(FolderLedger.perDay) Dateien erreicht; der Rest folgt morgen."
                break
            }
            let url = URL(fileURLWithPath: f.path)
            let loaded = await Task.detached(priority: .utility) { FileJobs.load(url) }.value
            guard case .success(let file) = loaded else { continue }
            do {
                _ = try await client.file(file.data, name: file.name, type: file.type, what: "wissen", sprache: nil,
                                          ordner: "/" + f.folder)
                ledger.done(f.path, size: f.size, mtime: f.mtime, sha256: sha, counts: !again)
                if !again { sent += 1 }
                changed = true
            } catch SparkProblem.conflict {
                ledger.done(f.path, size: f.size, mtime: f.mtime, sha256: sha, counts: false)   // already there
                changed = true
            } catch SparkProblem.failed(let m) {
                // the Spark does not take this file (type, size …): not again until it changes
                ledger.done(f.path, size: f.size, mtime: f.mtime, sha256: sha, counts: false)
                changed = true
                problem = "„\(file.name)“: \(m)"
            } catch {
                // not reachable, Notaus, busy, part off: try again with the next scan
                problem = AppModel.shared.absorb(error)
                break
            }
        }
        if files.count < Self.maxFilesPerScan {
            let before = ledger.files.count
            ledger.prune(existing: existing)
            if ledger.files.count != before { changed = true }
        }
        if changed { saveLedger() }
        if sent > 0 {
            let text = sent == 1 ? "1 Datei ins Wissen übernommen" : "\(sent) Dateien ins Wissen übernommen"
            lastText = text + "."
            Notifier.plain(title: "Spark-Wissen", body: text)
        }
        if !problem.isEmpty { lastText = problem }
    }

    /// the sub folder names to the panel when they changed (at most once a minute), else every 10 minutes (the panel
    /// keeps them in memory only); an older Spark without POST /api/desk/ordner is simply asked again later
    private func report(_ dirs: [String], client: SparkClient, now: Date) async {
        let since = now.timeIntervalSince(reportedAt)
        guard (dirs != reportedDirs && since > 60) || since > 600 else { return }
        reportedAt = now
        if (try? await client.postJSON("api/desk/ordner", ["dirs": dirs], timeout: 30)) != nil {
            reportedDirs = dirs
        }
    }
}

/// Ich → Dokumente → Ausgelassene Ordner (config.auslassen): the same rules as the panel (auslassen.py). A folder
/// ("a/b" below the watched one) with everything below it; a name for every folder in the path, case does not matter,
/// a "*" at the end means "begins with".
struct LeftOut: Equatable, Sendable {
    var names: [String] = []
    var folders: [String] = []

    init() {}

    init(_ v: Any?) {
        let d = v as? [String: Any] ?? [:]
        names = (d["names"] as? [String] ?? []).prefix(50)
            .map { String($0.precomposedStringWithCanonicalMapping.prefix(81)) }.filter { !$0.isEmpty }
        folders = (d["folders"] as? [String] ?? []).prefix(200)
            .map { $0.precomposedStringWithCanonicalMapping.split(separator: "/").joined(separator: "/") }.filter { !$0.isEmpty }
    }

    /// is the folder rel ("a/b") left out; "" (the watched folder itself) never is
    func covers(_ rel: String) -> Bool {
        let segs = rel.split(separator: "/").map(String.init)
        guard !segs.isEmpty else { return false }
        let p = segs.joined(separator: "/")
        if folders.contains(where: { p == $0 || p.hasPrefix($0 + "/") }) { return true }
        return segs.contains { seg in names.contains { Self.hit($0, seg) } }
    }

    static func hit(_ rule: String, _ seg: String) -> Bool {
        let r = rule.lowercased(), s = seg.lowercased()
        return r.hasSuffix("*") ? s.hasPrefix(String(r.dropLast())) : s == r
    }
}
