import Foundation

/// Ways into the panel in a text ("Im Panel unter Ich → Begleiter einschalten"): the way becomes a link to
/// `<Spark>/#weg=<way>`, the panel opens that place itself (way.js). Same rule as wege.py on the Spark;
/// "Einstellungen → …" without "Panel" right before it is the Begleiter's or the Mac's own settings.
/// Only navigation: the link opens the panel in the browser, nothing else.
enum Wege {
    static let roots = "Einstellungen|Funktionen|Zustand|Personen und Geräte|Ich|Settings|Features|Status|People and devices|Me|Kalender|Calendar|E-Mail|E-mail|Kontakte|Contacts|Wissensbuch|Knowledge book|Krisenspiel|Crisis game"
    private static let rx = try? NSRegularExpression(
        pattern: "(?<![\\w-])(?<!Mein )(?<!My )(?<!→ )(?:\(roots))\\s*→[^\\n.;:()!?]{1,160}")
    private static let plain = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~")

    /// The first way in a text and where it stands, or nil.
    static func find(_ text: String) -> (way: String, range: Range<String.Index>)? {
        guard let rx else { return nil }
        let ns = text as NSString
        for m in rx.matches(in: text, range: NSRange(location: 0, length: min(ns.length, 6000))) {
            guard let r = Range(m.range, in: text) else { continue }
            let from = text.index(r.lowerBound, offsetBy: -14, limitedBy: text.startIndex) ?? text.startIndex
            let way = String(text[r]).trimmingCharacters(in: CharacterSet(charactersIn: " ,–-"))
            if (way.hasPrefix("Einstellungen") || way.hasPrefix("Settings")) && !text[from..<r.lowerBound].lowercased().contains("panel") { continue }
            return (String(way.prefix(200)), r.lowerBound..<text.index(r.lowerBound, offsetBy: way.count))
        }
        return nil
    }

    /// `<base>/#weg=<way>`, or nil without a Spark.
    static func link(_ way: String, base: String?) -> URL? {
        guard let base, !way.isEmpty, let q = String(way.prefix(200)).addingPercentEncoding(withAllowedCharacters: plain) else { return nil }
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/#weg=" + q)
    }

    /// A text with its way as a link into the own Spark's panel; plain text when there is none or no Spark yet.
    @MainActor static func text(_ s: String) -> AttributedString {
        var a = AttributedString(s)
        guard let hit = find(s), let url = link(hit.way, base: AppModel.shared.base),
              let lo = AttributedString.Index(hit.range.lowerBound, within: a),
              let hi = AttributedString.Index(hit.range.upperBound, within: a)
        else { return a }
        a[lo..<hi].link = url
        return a
    }
}
