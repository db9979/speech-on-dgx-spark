import Foundation

// The parts of the update and the coffee link that need no AppKit: checked on Linux too (swiftc -typecheck).

/// "1.0.342": the program's version as the Spark compares it. "0.0.0" or nothing is a development build.
enum AppVersion {
    /// Digits and dots only, 1 to 4 parts, each part as a plain number ("01.0.342" -> "1.0.342"); nil when odd.
    static func normalize(_ raw: String?) -> String? {
        var s = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("v") || s.hasPrefix("V") { s.removeFirst() }
        let parts = s.split(separator: ".", omittingEmptySubsequences: false)
        guard (1...4).contains(parts.count) else { return nil }
        var nums: [Int] = []
        for p in parts {
            guard !p.isEmpty, p.count <= 6, p.allSatisfy({ $0.isASCII && $0.isNumber }), let n = Int(p) else { return nil }
            nums.append(n)
        }
        return nums.map(String.init).joined(separator: ".")
    }

    /// The version of a real (CI) build, or nil for a development build ("0.0.0", missing, odd).
    static func release(_ raw: String?) -> String? {
        guard let v = normalize(raw), numbers(v).contains(where: { $0 != 0 }) else { return nil }
        return v
    }

    static func numbers(_ v: String) -> [Int] {
        v.split(separator: ".").map { Int($0) ?? 0 }
    }

    /// -1, 0, 1 (missing parts count as 0: "1.0" == "1.0.0")
    static func compare(_ a: String, _ b: String) -> Int {
        let x = numbers(a)
        let y = numbers(b)
        for i in 0..<max(x.count, y.count) {
            let l = i < x.count ? x[i] : 0
            let r = i < y.count ? y[i] : 0
            if l != r { return l < r ? -1 : 1 }
        }
        return 0
    }

    static func isNewer(_ candidate: String, than current: String) -> Bool {
        compare(candidate, current) > 0
    }
}

/// config.update: what the Spark offers. Only taken when every field looks right.
struct UpdateInfo: Equatable {
    static let maxSize = 400 * 1024 * 1024

    let version: String
    let size: Int
    let sha256: String     // 64 lower-case hex digits

    init?(version: String, size: Int, sha256: String) {
        guard let v = AppVersion.normalize(version), (1...Self.maxSize).contains(size),
              let h = UpdateCheck.hex64(sha256) else { return nil }
        self.version = v
        self.size = size
        self.sha256 = h
    }

    /// From the JSON value of "update" (null or an object).
    init?(json: Any?) {
        guard let d = json as? [String: Any], let v = d["version"] as? String,
              let s = (d["size"] as? NSNumber)?.intValue, let h = d["sha256"] as? String else { return nil }
        self.init(version: v, size: s, sha256: h)
    }

    /// "64 MB" (rounded, at least 1)
    var sizeText: String {
        let mb = Double(size) / 1_000_000
        if mb < 1 { return "1 MB" }
        return "\(Int(mb.rounded())) MB"
    }
}

enum UpdateCheck {
    /// The bundle id the new app must have.
    static let bundleID = "de.db9979.spark.begleiter"

    /// 64 hex digits in lower case, or nil.
    static func hex64(_ s: String) -> String? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard t.count == 64, t.allSatisfy({ $0.isASCII && $0.isHexDigit }) else { return nil }
        return t
    }

    static func hex(_ bytes: [UInt8]) -> String {
        let digits = Array("0123456789abcdef")
        var out = ""
        out.reserveCapacity(bytes.count * 2)
        for b in bytes {
            out.append(digits[Int(b >> 4)])
            out.append(digits[Int(b & 0x0f)])
        }
        return out
    }

    /// Size AND SHA-256 of the downloaded bytes must equal what config.update said.
    static func matches(size: Int, sha256 digest: [UInt8], _ info: UpdateInfo) -> Bool {
        guard size == info.size, digest.count == 32 else { return false }
        // compare all characters, not only up to the first difference
        let got = Array(hex(digest).utf8)
        let want = Array(info.sha256.utf8)
        guard got.count == want.count else { return false }
        var diff: UInt8 = 0
        for i in 0..<got.count { diff |= got[i] ^ want[i] }
        return diff == 0
    }

    /// The unpacked app must be ours and the version the Spark announced.
    static func bundleMatches(id: String?, version: String?, _ info: UpdateInfo) -> Bool {
        guard id == bundleID, let v = AppVersion.normalize(version) else { return false }
        return AppVersion.compare(v, info.version) == 0
    }

    /// Whether an update is to be offered at all.
    static func offer(_ info: UpdateInfo?, current: String?) -> UpdateInfo? {
        guard let info, let current = AppVersion.release(current) else { return nil }   // development build: never
        return AppVersion.isNewer(info.version, than: current) ? info : nil
    }

    /// Updates only through https: over http someone in the home network could swap the file and its checksum.
    static func secureBase(_ base: String) -> Bool {
        base.lowercased().hasPrefix("https://")
    }

    /// "ABCDE12345": an Apple Team ID (10 upper-case letters or digits), else nil (ad hoc or unsigned).
    static func teamID(_ raw: String?) -> String? {
        guard let t = raw, t.count == 10,
              t.unicodeScalars.allSatisfy({ ("A"..."Z").contains($0) || ("0"..."9").contains($0) }) else { return nil }
        return t
    }

    /// Whose signature a new app may carry: a program signed by a team (Developer ID) takes only an update signed
    /// by the same team; an ad-hoc signed program (no team) proves no origin, so its update is checked by size,
    /// SHA-256, bundle id and a valid signature only.
    static func signerAccepted(running: String?, new: String?) -> Bool {
        guard let running = teamID(running) else { return true }
        return teamID(new) == running
    }

    /// codesign's requirement text (-R=…) for an app of this team: Apple's chain and the team in the leaf.
    static func requirement(team: String) -> String? {
        guard let t = teamID(team) else { return nil }
        return "=anchor apple generic and certificate leaf[subject.OU] = \"\(t)\""
    }

    /// The helper that swaps the app after it quit: waits for the old process (at most 60 s), moves the old app
    /// aside, the new one in place, removes the old one and starts the app again. If the move fails the old app is
    /// put back. All paths come as arguments, never as part of the text.
    ///   sh helper.sh <pid> <old .app> <new .app> <backup path>
    static let helperScript = """
        #!/bin/sh
        pid="$1"; old="$2"; new="$3"; bak="$4"
        [ -n "$pid" ] && [ -n "$old" ] && [ -n "$new" ] && [ -n "$bak" ] || exit 2
        i=0
        while /bin/kill -0 "$pid" 2>/dev/null; do
          i=$((i + 1))
          [ "$i" -gt 600 ] && exit 3
          /bin/sleep 0.1
        done
        [ -d "$new" ] || { /usr/bin/open "$old"; exit 4; }
        /bin/rm -rf "$bak"
        if /bin/mv "$old" "$bak"; then
          if /bin/mv "$new" "$old"; then
            /bin/rm -rf "$bak"
            /usr/bin/open "$old"
            exit 0
          fi
          /bin/rm -rf "$old"
          /bin/mv "$bak" "$old"
        fi
        /usr/bin/open "$old"
        exit 5
        """
}

/// The coffee link: config.coffee only when it is an https link to buymeacoffee.com, else the fixed one.
enum CoffeeLink {
    static let fallback = URL(string: "https://buymeacoffee.com/zquu1xu570")!

    static func accept(_ raw: Any?) -> URL {
        guard let s = raw as? String, s.count <= 200,
              s.unicodeScalars.allSatisfy({ $0.isASCII && $0.value > 32 && $0.value < 127 }),
              let c = URLComponents(string: s),
              c.scheme == "https", c.host == "buymeacoffee.com",
              c.user == nil, c.password == nil, c.port == nil, c.fragment == nil,
              c.path.hasPrefix("/"), c.path.count > 1,
              let url = c.url else {
            return fallback
        }
        return url
    }
}
