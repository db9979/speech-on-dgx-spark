import Foundation

/// Wohin das Programm darf: Adresse und Einmal-Schlüssel stehen nur im Namen der eigenen App, so wie der Spark sie je
/// Hilfe packt (spontansteuern.mac_zip: `SparkHilfe-<host>-<Schlüssel>.app`, ein Doppelpunkt vor dem Port wird zu „_“;
/// der Finder hängt bei einer zweiten Kopie „ 2“ an). Der Schlüssel hat 22 Zeichen (128 Bit, `spontansteuern.KEY`).
/// Fehlt etwas oder passt etwas nicht, verbindet sich das Programm nirgends hin.
struct Ziel: Equatable, CustomStringConvertible {
    let host: String
    let port: Int
    let key: String

    private static let name = try! NSRegularExpression(
        pattern: #"^SparkHilfe-([A-Za-z0-9._\-]{1,260})-([A-Za-z0-9_\-]{22})(?: \d{1,3})?\.app$"#)
    private static let hostPort = try! NSRegularExpression(pattern: #"^([a-z0-9.\-]{1,253})(?:_([0-9]{1,5}))?$"#)
    private static let label = try! NSRegularExpression(pattern: #"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$"#)

    /// „spark.example.org“ oder „spark.example.org:8443“, so wie es die Fragen zeigen
    var shown: String { port == 443 ? host : "\(host):\(port)" }

    /// Der einzige Weg, den das Programm öffnet: wss, normale Zertifikatsprüfung.
    var socket: URL? {
        var c = URLComponents()
        c.scheme = "wss"
        c.host = host
        c.port = port == 443 ? nil : port
        c.path = "/api/hilfe/steuern"
        return c.url
    }

    /// Nie der Schlüssel in einem Text (Fehlermeldung, Fenster).
    var description: String { shown }

    /// Aus dem Namen der App (ohne Ordner); nil, wenn er keine Hilfe nennt.
    static func aus(_ fileName: String) -> Ziel? {
        guard !fileName.isEmpty, fileName.count <= 300,
              let m = match(name, fileName), m.count == 3 else { return nil }
        guard let h = match(hostPort, m[1].lowercased()), h.count == 3 else { return nil }
        let host = h[1]
        guard host.split(separator: ".", omittingEmptySubsequences: false).allSatisfy({ match(label, String($0)) != nil })
        else { return nil }
        var port = 443
        if !h[2].isEmpty {
            guard let p = Int(h[2]), (1...65535).contains(p) else { return nil }
            port = p
        }
        return Ziel(host: host, port: port, key: m[2])
    }

    /// Aus dem Ort der laufenden App (auch wenn macOS sie zum ersten Start an einen anderen Ort verlegt: der Name bleibt).
    static func ausProgramm() -> Ziel? {
        aus(Bundle.main.bundleURL.lastPathComponent)
    }

    /// the groups of a whole-string match ("" for a group that did not take part)
    private static func match(_ rx: NSRegularExpression, _ s: String) -> [String]? {
        let r = NSRange(s.startIndex..., in: s)
        guard let m = rx.firstMatch(in: s, range: r), m.range == r else { return nil }
        return (0..<m.numberOfRanges).map { i in
            Range(m.range(at: i), in: s).map { String(s[$0]) } ?? ""
        }
    }
}
