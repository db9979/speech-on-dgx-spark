import AppKit
import Combine
import CryptoKit

/// Updates (contract "Version 2"): the Spark says in config.update which version it has, with size and SHA-256.
/// The file comes only from the paired Spark (GET /api/desk/update?arch=mac), is checked (size, SHA-256, bundle id,
/// version, signature), and replaces the app only after the person clicked "Aktualisieren". On any failure the
/// running app stays as it is.
@MainActor
final class Updater: ObservableObject {
    static let shared = Updater()
    static let autoKey = "update.autoLoad"

    enum Phase: Equatable {
        case idle                       // nothing to do (or a development build)
        case available                  // offered, not loaded yet
        case downloading
        case ready                      // loaded and checked, waits for the click
        case installing
        case failed(String)
    }

    @Published private(set) var info: UpdateInfo?
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var checking = false
    @Published private(set) var lastCheck: Date?
    /// "Updates automatisch laden, vor dem Installieren fragen" (only on this Mac)
    @Published var autoLoad: Bool {
        didSet {
            UserDefaults.standard.set(autoLoad, forKey: Self.autoKey)
            if autoLoad, phase == .available { startDownload(thenInstall: false) }
        }
    }

    private var task: Task<Void, Never>?
    private var loaded: URL?

    init() {
        autoLoad = (UserDefaults.standard.object(forKey: Self.autoKey) as? Bool) ?? true
    }

    /// The version of this program ("1.0.342") or nil for a development build.
    static var currentVersion: String? {
        AppVersion.release(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String)
    }

    /// For the query of config and poll ("0.0.0" for a development build: the Spark may answer, we never offer).
    static var versionParam: String {
        AppVersion.normalize(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "0.0.0"
    }

    nonisolated static var updateDir: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Spark Begleiter", isDirectory: true)
            .appendingPathComponent("update", isDirectory: true)
    }

    /// Leftovers of an earlier run (the folder "bereit" with an app for manual install stays).
    nonisolated static func cleanOnStart() {
        let fm = FileManager.default
        guard let items = try? fm.contentsOfDirectory(at: updateDir, includingPropertiesForKeys: nil) else { return }
        for u in items where u.lastPathComponent != "bereit" {
            try? fm.removeItem(at: u)
        }
    }

    var dot: Bool {
        info != nil && phase != .idle
    }

    var statusText: String {
        if Self.currentVersion == nil { return "Entwicklungsversion: keine Updates" }
        guard let info else { return "Neueste Version" }
        switch phase {
        case .idle: return "Neueste Version"
        case .available: return "Neue Version \(info.version)"
        case .downloading: return "Lädt Version \(info.version) …"
        case .ready: return "Version \(info.version) bereit"
        case .installing: return "Installiert Version \(info.version) …"
        case .failed(let m): return m
        }
    }

    // ------------------------------------------------------------------ from config

    /// config.update (already parsed); nil = nothing to offer.
    func take(_ offered: UpdateInfo?) {
        lastCheck = Date()
        guard let next = UpdateCheck.offer(offered, current: Self.currentVersion) else {
            reset()
            return
        }
        if next == info { return }          // the same as before (also after a failure: no endless retries)
        reset()
        info = next
        phase = .available
        if autoLoad { startDownload(thenInstall: false) }
    }

    /// "Nach Updates suchen": config again; a failed attempt may run once more.
    func check() async {
        guard !checking else { return }
        checking = true
        if case .failed = phase {
            info = nil
            phase = .idle
        }
        await AppModel.shared.refreshConfig()
        lastCheck = Date()
        checking = false
    }

    /// Forgets the offer (also when the pairing ends).
    func reset() {
        task?.cancel()
        task = nil
        info = nil
        phase = .idle
        if let l = loaded { try? FileManager.default.removeItem(at: l) }
        loaded = nil
    }

    // ------------------------------------------------------------------ the click

    /// "Aktualisieren": load (if not yet) and install.
    func install() {
        switch phase {
        case .ready:
            Task { await installNow() }
        case .available, .failed:
            startDownload(thenInstall: true)
        default:
            break
        }
    }

    private func startDownload(thenInstall: Bool) {
        guard let info, let client = AppModel.shared.client else { return }
        if phase == .downloading { return }
        task?.cancel()
        phase = .downloading
        task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let zip = try await Self.download(info, client: client)
                guard self.info == info else { return }
                self.loaded = zip
                self.phase = .ready
                if thenInstall { await self.installNow() }
            } catch is CancellationError {
                if self.info == info && self.phase == .downloading { self.phase = .available }
            } catch let p as SparkProblem {
                guard self.info == info else { return }
                self.phase = .failed(AppModel.shared.absorb(p))
            } catch {
                guard self.info == info else { return }
                self.phase = .failed("Update beschädigt, nichts geändert.")
            }
        }
    }

    /// Loads the zip from the paired Spark and checks size and SHA-256; a wrong file is deleted at once.
    private static func download(_ info: UpdateInfo, client: SparkClient) async throws -> URL {
        let fm = FileManager.default
        try? fm.createDirectory(at: updateDir, withIntermediateDirectories: true)
        let zip = updateDir.appendingPathComponent("Spark-Begleiter-mac.zip")
        try await client.download("api/desk/update?arch=mac", to: zip, maxBytes: info.size)
        let ok = await Task.detached(priority: .utility) { () -> Bool in
            guard let got = Updater.sha256(of: zip) else { return false }
            return UpdateCheck.matches(size: got.size, sha256: got.digest, info)
        }.value
        guard ok else {
            try? fm.removeItem(at: zip)
            throw SparkProblem.failed("Update beschädigt, nichts geändert.")
        }
        return zip
    }

    /// size and SHA-256 of a file, read in pieces
    nonisolated private static func sha256(of url: URL) -> (size: Int, digest: [UInt8])? {
        guard let h = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? h.close() }
        var hasher = SHA256()
        var size = 0
        while true {
            guard let chunk = try? h.read(upToCount: 1 << 20) else { return nil }
            if chunk.isEmpty { break }
            size += chunk.count
            hasher.update(data: chunk)
        }
        return (size: size, digest: Array(hasher.finalize()))
    }

    // ------------------------------------------------------------------ install

    private func installNow() async {
        guard phase == .ready, let info, let zip = loaded else { return }
        phase = .installing
        let result = await Task.detached(priority: .userInitiated) { () -> Result<URL, InstallError> in
            Self.unpack(zip, info: info)
        }.value
        let app: URL
        switch result {
        case .failure(let e):
            try? FileManager.default.removeItem(at: zip)
            loaded = nil
            phase = .failed(e.message)
            return
        case .success(let u):
            app = u
        }

        let current = Bundle.main.bundleURL
        guard Self.replaceable(current) else {
            revealForManualInstall(app, info: info)
            return
        }
        do {
            try launchHelper(newApp: app, oldApp: current)
        } catch {
            phase = .failed("Das Update ließ sich nicht starten. Es bleibt bei der alten Version.")
            return
        }
        // the helper waits until we are gone, then swaps the app and starts it again
        NSApp.terminate(nil)
    }

    struct InstallError: Error {
        let message: String
    }

    /// ditto -x -k into a fresh folder, then: exactly one .app, our bundle id, the announced version, a valid
    /// signature.
    nonisolated private static func unpack(_ zip: URL, info: UpdateInfo) -> Result<URL, InstallError> {
        let fm = FileManager.default
        let dir = updateDir.appendingPathComponent("neu-" + UUID().uuidString, isDirectory: true)
        let broken = InstallError(message: "Update beschädigt, nichts geändert.")
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        } catch {
            return .failure(InstallError(message: "Das Update ließ sich nicht auspacken."))
        }
        guard run("/usr/bin/ditto", ["-x", "-k", zip.path, dir.path]) == 0 else {
            try? fm.removeItem(at: dir)
            return .failure(broken)
        }
        let apps = ((try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [])
            .filter { $0.pathExtension == "app" }
        guard apps.count == 1, let app = apps.first,
              let data = try? Data(contentsOf: app.appendingPathComponent("Contents/Info.plist")),
              let plist = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: Any],
              UpdateCheck.bundleMatches(id: plist["CFBundleIdentifier"] as? String,
                                        version: plist["CFBundleShortVersionString"] as? String, info),
              let exe = plist["CFBundleExecutable"] as? String, !exe.contains("/"),
              fm.isExecutableFile(atPath: app.appendingPathComponent("Contents/MacOS/" + exe).path),
              run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app.path]) == 0 else {
            try? fm.removeItem(at: dir)
            return .failure(broken)
        }
        return .success(app)
    }

    /// Runs a system tool without a shell; its exit code (-1 if it could not start).
    nonisolated private static func run(_ tool: String, _ args: [String]) -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool)
        p.arguments = args
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
        } catch {
            return -1
        }
        p.waitUntilExit()
        return p.terminationStatus
    }

    /// Whether the running app can be swapped in place (a real .app in a writable folder, not translocated).
    private static func replaceable(_ app: URL) -> Bool {
        let fm = FileManager.default
        let parent = app.deletingLastPathComponent()
        return app.pathExtension == "app"
            && !app.path.contains("/AppTranslocation/")
            && fm.isWritableFile(atPath: parent.path)
            && fm.isWritableFile(atPath: app.path)
    }

    private func launchHelper(newApp: URL, oldApp: URL) throws {
        let fm = FileManager.default
        let script = Self.updateDir.appendingPathComponent("tausch.sh")
        try UpdateCheck.helperScript.write(to: script, atomically: true, encoding: .utf8)
        let backup = oldApp.deletingLastPathComponent()
            .appendingPathComponent(".Spark-Begleiter-alt-\(ProcessInfo.processInfo.processIdentifier).app")
        if fm.fileExists(atPath: backup.path) { try? fm.removeItem(at: backup) }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [script.path, String(ProcessInfo.processInfo.processIdentifier), oldApp.path, newApp.path, backup.path]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try p.run()
    }

    /// The program's folder cannot be written: the new app goes to …/update/bereit and is shown in the Finder.
    private func revealForManualInstall(_ app: URL, info: UpdateInfo) {
        let fm = FileManager.default
        let ready = Self.updateDir.appendingPathComponent("bereit", isDirectory: true)
        try? fm.removeItem(at: ready)
        try? fm.createDirectory(at: ready, withIntermediateDirectories: true)
        let target = ready.appendingPathComponent(app.lastPathComponent)
        do {
            try fm.moveItem(at: app, to: target)
        } catch {
            phase = .failed("Das Update ließ sich nicht bereitlegen. Es bleibt bei der alten Version.")
            return
        }
        try? fm.removeItem(at: app.deletingLastPathComponent())
        phase = .failed("Der Ordner des Programms ist nicht beschreibbar. Die neue Version liegt im Finder bereit: "
                        + "Begleiter beenden und sie in den Ordner „Programme“ ziehen.")
        NSWorkspace.shared.activateFileViewerSelecting([target])
    }
}
