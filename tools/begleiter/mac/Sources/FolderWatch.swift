import AppKit
import CryptoKit

/// Part "folder": a local folder (default ~/Spark-Wissen) is looked at every 15 s; new or changed files go to the
/// Wissen (POST /api/desk/file what=wissen) once they were quiet for 10 s. What was sent is remembered locally
/// (path → size + mtime + SHA-256) in Application Support/Spark Begleiter; at most 50 files a day.
@MainActor
final class FolderWatch: ObservableObject {
    static let shared = FolderWatch()
    static let pathKey = "folder.path"
    static let interval: TimeInterval = 15
    static let maxFilesPerScan = 2000

    @Published private(set) var active = false
    /// the last thing worth saying ("3 Dateien ins Wissen übernommen.", "Für heute …")
    @Published private(set) var lastText = ""
    @Published private(set) var path: URL

    private var timer: Timer?
    private var scanning = false
    private var ledger = FolderLedger()
    private var quiet = QuietCheck()
    private var loaded = false

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
    }

    /// regular files in the folder (and below), hidden and temporary ones left out
    nonisolated static func list(_ root: URL) -> [Seen] {
        let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey, .isHiddenKey]
        guard let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: keys,
                                                     options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return [] }
        var out: [Seen] = []
        for case let u as URL in e {
            if out.count >= maxFilesPerScan { break }
            let name = u.lastPathComponent
            guard let v = try? u.resourceValues(forKeys: Set(keys)) else { continue }
            if FileKinds.skip(name) || v.isHidden == true {
                continue
            }
            guard v.isRegularFile == true, let size = v.fileSize, size > 0, size <= FileKinds.maxBytes,
                  FileKinds.mime(for: name) != nil,
                  let m = v.contentModificationDate else { continue }
            out.append(Seen(path: u.path, size: size, mtime: m.timeIntervalSince1970))
        }
        return out
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
        let files = await Task.detached(priority: .utility) { Self.list(root) }.value
        let now = Date()
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
            guard ledger.left > 0 else {
                problem = "Für heute sind \(FolderLedger.perDay) Dateien erreicht; der Rest folgt morgen."
                break
            }
            let url = URL(fileURLWithPath: f.path)
            let loaded = await Task.detached(priority: .utility) { FileJobs.load(url) }.value
            guard case .success(let file) = loaded else { continue }
            do {
                _ = try await client.file(file.data, name: file.name, type: file.type, what: "wissen", sprache: nil)
                ledger.done(f.path, size: f.size, mtime: f.mtime, sha256: sha, counts: true)
                sent += 1
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
}
