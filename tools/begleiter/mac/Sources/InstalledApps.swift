import AppKit
import CryptoKit

/// Part "act": the programs installed on this Mac, so the panel can offer them to pick from instead of typing a
/// name and a path. Only names and .app paths leave the Mac (POST /api/desk/apps), only while the part is on: at
/// start, when the part turns on, and once a day (an unchanged list is not sent again within the day).
@MainActor
final class InstalledApps {
    static let shared = InstalledApps()
    static let sentKey = "apps.sent"
    static let hashKey = "apps.hash"

    private var active = false
    private var timer: Timer?
    private var sending = false

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: 3600, repeats: true) { _ in
                Task { @MainActor in InstalledApps.shared.sendIfDue(force: false) }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            sendIfDue(force: true)              // start of the program, or the part just turned on
        } else {
            active = false
            timer?.invalidate()
            timer = nil
        }
    }

    private func sendIfDue(force: Bool) {
        guard active, !sending, AppModel.shared.part("act"), let client = AppModel.shared.client else { return }
        sending = true
        Task { @MainActor in
            defer { self.sending = false }
            let list = await Task.detached(priority: .utility) { InstalledApps.scan() }.value
            let hash = Self.hash(list)
            let d = UserDefaults.standard
            let last = d.object(forKey: Self.sentKey) as? Date
            guard force || InstalledList.due(lastSent: last, lastHash: d.string(forKey: Self.hashKey), hash: hash, now: Date()),
                  self.active else { return }
            do {
                _ = try await client.postJSON("api/desk/apps", ["apps": list], timeout: 60)
                d.set(Date(), forKey: Self.sentKey)
                d.set(hash, forKey: Self.hashKey)
            } catch {
                AppModel.shared.absorb(error)
            }
        }
    }

    nonisolated static func hash(_ list: [[String: String]]) -> String {
        var s = ""
        for e in list { s += (e["name"] ?? "") + "\u{1}" + (e["path"] ?? "") + "\u{2}" }
        return SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    /// *.app in the usual folders (depth 2, never inside a bundle); name = the bundle's display name or file name
    nonisolated static func scan() -> [[String: String]] {
        let fm = FileManager.default
        let roots = ["/Applications", "/Applications/Utilities", "/System/Applications",
                     "/System/Applications/Utilities", NSHomeDirectory() + "/Applications"]
        var found: [(name: String, path: String)] = []
        func look(_ dir: String, depth: Int) {
            guard let names = try? fm.contentsOfDirectory(atPath: dir) else { return }
            for n in names.sorted() where !n.hasPrefix(".") {
                let p = (dir as NSString).appendingPathComponent(n)
                if n.lowercased().hasSuffix(".app") {
                    found.append((displayName(p, file: n), p))
                } else if depth < 2 {
                    var isDir: ObjCBool = false
                    if fm.fileExists(atPath: p, isDirectory: &isDir), isDir.boolValue,
                       !roots.contains(p) {                     // Utilities is its own root
                        look(p, depth: depth + 1)
                    }
                }
                if found.count > 3000 { return }
            }
        }
        for r in roots { look(r, depth: 1) }
        return InstalledList.normalize(found)
    }

    nonisolated private static func displayName(_ path: String, file: String) -> String {
        if let b = Bundle(path: path) {
            for k in ["CFBundleDisplayName", "CFBundleName"] {
                if let s = b.localizedInfoDictionary?[k] as? String ?? b.infoDictionary?[k] as? String,
                   !s.trimmingCharacters(in: .whitespaces).isEmpty {
                    return s
                }
            }
        }
        return String(file.dropLast(4))
    }
}
