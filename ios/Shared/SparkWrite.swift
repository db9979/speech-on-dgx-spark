import Foundation

/// What the writing help ("Schreibhilfe", app/panel/schreib.py) does with a text. The two translations are
/// the Spark's "uebersetzen" with a language.
enum WriteArt: String, CaseIterable, Identifiable {
    case korrigieren, glaetten, kuerzer, freundlicher, foermlicher, englisch, deutsch

    var id: String { rawValue }

    /// the art the Spark knows
    var art: String {
        switch self {
        case .englisch, .deutsch: return "uebersetzen"
        default: return rawValue
        }
    }

    var sprache: String? {
        switch self {
        case .englisch: return "en"
        case .deutsch: return "de"
        default: return nil
        }
    }

    var label: String {
        switch self {
        case .korrigieren: return String(localized: "Korrigieren")
        case .glaetten: return String(localized: "Glätten")
        case .kuerzer: return String(localized: "Kürzer")
        case .freundlicher: return String(localized: "Freundlicher")
        case .foermlicher: return String(localized: "Förmlicher")
        case .englisch: return String(localized: "Ins Englische")
        case .deutsch: return String(localized: "Ins Deutsche")
        }
    }
}

/// The improved text and, for everything but translations, the changes word by word.
struct WriteResult {
    let text: String
    /// ("=", same), ("-", removed), ("+", added); nil for translations or very many changes
    let diff: [(op: String, text: String)]?
    let changes: Int?
}

extension SparkAPI {
    /// as much text as the Spark takes at once (schreib.MAX_TEXT)
    static let writeMax = 20000

    static var writeOff: String { String(localized: "Der Admin hat die Schreibhilfe noch nicht freigegeben.") }

    /// Is the writing help on for this profile (admin and profile switches)? false also on 403.
    func writeOn() async throws -> Bool {
        var r = request("api/write")
        r.timeoutInterval = 15
        let (data, response) = try await URLSession.shared.data(for: r)
        if (response as? HTTPURLResponse)?.statusCode == 403 { return false }
        try Self.checkWrite(data, response)
        return Self.object(data)["on"] as? Bool ?? false
    }

    /// The text improved by the Spark. The model can take up to a minute.
    func improve(_ text: String, art: WriteArt) async throws -> WriteResult {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { throw SparkError(message: String(localized: "Der Text ist leer.")) }
        guard t.unicodeScalars.count <= Self.writeMax else {
            throw SparkError(message: String(localized: "Der Text ist zu lang (höchstens \(Self.writeMax) Zeichen)."))
        }
        var body: [String: Any] = ["text": t, "art": art.art]
        if let s = art.sprache { body["sprache"] = s }
        var r = request("api/write/assist", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.timeoutInterval = 180
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.checkWrite(data, response)
        let d = Self.object(data)
        guard let out = d["text"] as? String else { throw SparkError(message: String(localized: "Keine Antwort vom Spark.")) }
        let diff: [(op: String, text: String)]? = (d["diff"] as? [[Any]])?.compactMap { p -> (op: String, text: String)? in
            guard p.count == 2, let op = p[0] as? String, ["=", "-", "+"].contains(op), let s = p[1] as? String else { return nil }
            return (op: op, text: s)
        }
        return WriteResult(text: out, diff: diff, changes: (d["changes"] as? NSNumber)?.intValue)
    }

    /// As check, but 403 means the writing help is off, and busy (429) or Notaus (503) bring the Spark's own words.
    static func checkWrite(_ data: Data, _ response: URLResponse) throws {
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let detail = (object(data)["detail"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if status == 403 {
            throw SparkError(message: detail.isEmpty ? writeOff : writeOff + "\n" + detail)
        }
        if (status == 429 || status == 503) && !detail.isEmpty {
            throw SparkError(message: detail)
        }
        try check(data, response)
    }
}
