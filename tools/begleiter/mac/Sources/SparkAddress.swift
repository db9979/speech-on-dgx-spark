import Foundation

/// The Spark's address and the setup line from the panel ("<base>#begleiter=XXXX-XXXX").
/// Plain http only for home-network hosts (localhost, 127., 10., 192.168., 172.16–31., *.local).
enum SparkAddress {
    static let marker = "#begleiter="
    static let alphabet: Set<Character> = Set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")

    struct Failure: Error {
        let message: String
    }

    /// "scheme://host[:port]" in lower case without path, or nil when it is not such an address.
    static func normalize(_ raw: String) -> String? {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        let lower = s.lowercased()
        let scheme: String
        if lower.hasPrefix("https://") {
            scheme = "https"
        } else if lower.hasPrefix("http://") {
            scheme = "http"
        } else {
            return nil
        }
        let rest = String(lower.dropFirst(scheme.count + 3))
        var host = rest
        var port: String?
        if let colon = rest.firstIndex(of: ":") {
            host = String(rest[..<colon])
            port = String(rest[rest.index(after: colon)...])
        }
        guard !host.isEmpty, host.count <= 253, !host.hasPrefix("."), !host.hasPrefix("-"), !host.hasSuffix("."),
              host.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "." || $0 == "-") }) else {
            return nil
        }
        var out = scheme + "://" + host
        if let p = port {
            guard !p.isEmpty, p.count <= 5, p.allSatisfy({ $0.isASCII && $0.isNumber }),
                  let n = Int(p), (1...65535).contains(n) else {
                return nil
            }
            out += ":\(n)"
        }
        return out
    }

    /// The host part of a normalized base.
    static func host(of base: String) -> String {
        guard let r = base.range(of: "://") else { return "" }
        let rest = base[r.upperBound...]
        if let colon = rest.firstIndex(of: ":") { return String(rest[..<colon]) }
        return String(rest)
    }

    /// localhost, 127.x, 10.x, 192.168.x, 172.16–31.x and *.local count as the home network.
    static func isHome(_ host: String) -> Bool {
        let h = host.lowercased()
        if h == "localhost" || (h.hasSuffix(".local") && h.count > 6) { return true }
        let parts = h.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return false }
        var b: [Int] = []
        for p in parts {
            guard !p.isEmpty, p.count <= 3, p.allSatisfy({ $0.isASCII && $0.isNumber }), let v = Int(p), v <= 255 else {
                return false
            }
            b.append(v)
        }
        return b[0] == 127 || b[0] == 10 || (b[0] == 192 && b[1] == 168) || (b[0] == 172 && (16...31).contains(b[1]))
    }

    /// The base if it may be used: https anywhere, http only at home.
    static func checkBase(_ raw: String) throws -> String {
        guard let base = normalize(raw) else {
            throw Failure(message: "Die Adresse des Spark sieht nicht richtig aus (so: https://spark.example.de).")
        }
        if base.hasPrefix("http://") && !isHome(host(of: base)) {
            throw Failure(message: "Unverschlüsselt (http) nur im Heimnetz. Bitte die https-Adresse des Spark nehmen.")
        }
        return base
    }

    /// "XXXX-XXXX" from what was typed (dash and spaces optional, lower case is fine), or nil.
    static func normalizeCode(_ raw: String) -> String? {
        let c = raw.uppercased().filter { $0 != "-" && !$0.isWhitespace }
        guard c.count == 8, c.allSatisfy({ alphabet.contains($0) }) else { return nil }
        return String(c.prefix(4)) + "-" + String(c.suffix(4))
    }

    static func check(base: String, code: String) throws -> (base: String, code: String) {
        let b = try checkBase(base)
        guard let c = normalizeCode(code) else {
            throw Failure(message: "Der Code hat 8 Zeichen, zum Beispiel ABCD-EFGH.")
        }
        return (b, c)
    }

    /// Base and code from the whole setup line.
    static func parse(line: String) throws -> (base: String, code: String) {
        let s = line.filter { !$0.isWhitespace }
        guard let r = s.range(of: marker, options: .caseInsensitive) else {
            throw Failure(message: "Das ist keine Einrichtungszeile. Sie sieht so aus: https://spark.example.de#begleiter=ABCD-EFGH")
        }
        return try check(base: String(s[..<r.lowerBound]), code: String(s[r.upperBound...]))
    }

    /// The computer's name as the Spark takes it: letters, digits, space, ".", "-", "_", at most 40.
    static func deviceName(_ raw: String?) -> String {
        let nfc = (raw ?? "").precomposedStringWithCanonicalMapping
        let kept = nfc.map { c -> Character in
            let single = c.unicodeScalars.count == 1
            let ok = single && (c.isLetter || c.isNumber || c == " " || c == "." || c == "-" || c == "_")
            return ok ? c : " "
        }
        let collapsed = String(kept).split(separator: " ").joined(separator: " ")
        let cut = String(collapsed.prefix(40)).trimmingCharacters(in: .whitespaces)
        return cut.isEmpty ? "Mac" : cut
    }
}
