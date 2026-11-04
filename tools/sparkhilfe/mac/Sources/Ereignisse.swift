import Foundation

/// Was vom Panel kommt, noch einmal geprüft (wie fernsicht.clean_events): nur die festen Listen des Kerns (Sicht.swift),
/// ein Punkt 0..1, höchstens `maxEvents` je Nachricht; Unbekanntes fällt weg.
enum Ereignisse {
    /// Eingaben je Nachricht höchstens (fernsicht.MAX_EVENTS).
    static let maxEvents = 40
    /// Ein Bild höchstens so groß (fernsicht.MAX_FRAME); größere schickt das Programm nie.
    static let maxFrame = 700 * 1024
    /// Eine Nachricht vom Panel höchstens so groß (spontanhilfe.MAX_MSG); größere beenden die Hilfe.
    static let maxMessage = 16 * 1024

    static func clean(_ m: [String: Any]) -> [[String: Any]] {
        guard let list = m["events"] as? [Any] else { return [] }
        var out: [[String: Any]] = []
        for raw in list.prefix(maxEvents) {
            guard let e = raw as? [String: Any], let t = e["t"] as? String else { continue }
            switch t {
            case "move", "click":
                guard let x = num(e["x"]), let y = num(e["y"]), (0...1).contains(x), (0...1).contains(y) else { continue }
                let b = e["b"] == nil ? "left" : (e["b"] as? String ?? "")
                if t == "click" && !ViewKeys.buttons.contains(b) { continue }
                out.append(["t": t, "x": x, "y": y, "b": b])
            case "scroll":
                guard let dy = num(e["dy"]), dy == dy.rounded(), (-10...10).contains(dy), dy != 0 else { continue }
                out.append(["t": "scroll", "dy": Int(dy)])
            case "key":
                guard let k = e["k"] as? String, ViewKeys.keys[k] != nil else { continue }
                out.append(["t": "key", "k": k])
            case "text":
                let s = String(String.UnicodeScalarView((e["s"] as? String ?? "").unicodeScalars.filter {
                    $0 == "\n" || !CharacterSet.controlCharacters.contains($0)
                }).prefix(ViewKeys.textMax))
                if !s.isEmpty { out.append(["t": "text", "s": s]) }
            default:
                continue
            }
        }
        return out
    }

    /// nur druckbare Zeichen, ohne Richtungszeichen, höchstens `max` (der Name des Helfers kommt vom Panel)
    static func plain(_ s: String, max: Int) -> String {
        let bidi: Set<Unicode.Scalar> = ["\u{202A}", "\u{202B}", "\u{202C}", "\u{202D}", "\u{202E}",
                                         "\u{2066}", "\u{2067}", "\u{2068}", "\u{2069}"]
        let kept = s.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) && !bidi.contains($0) }
        return String(String(String.UnicodeScalarView(kept)).prefix(max)).trimmingCharacters(in: .whitespaces)
    }

    /// a JSON number, never a Bool (NSNumber from JSONSerialization)
    private static func num(_ v: Any?) -> Double? {
        guard let n = v as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
        return n.doubleValue
    }
}
