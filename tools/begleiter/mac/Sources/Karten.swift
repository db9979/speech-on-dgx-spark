import Foundation

/// Cards under an answer in Frag Spark (Begleiter nachziehen 5a): Rückfrage ("Ja"/"Nein", "A oder B?"), Freigabe
/// ("Termin wartet auf dein Ja") and ways ("Im Kalender ansehen"). The Spark builds them from fixed words
/// (chat.desk_cards); a button only sends its word like a typed answer, opens one of `pages` in the panel or puts
/// the cursor in the field. Same rules as Karten.cs of the Windows program.
enum AskCards {
    static let maxCards = 3
    static let maxButtons = 5
    static let maxLabel = 30
    /// the panel pages a way button may open (chat.DESK_GOTO)
    static let pages = ["#me=calbox", "#me=mailbox", "#me=fundbox", "#me=factbox"]

    /// Finden's Sofort-Karte (chat.DESK_ORIGINAL): "Original öffnen" leads to "#fund=" and one entry's number, nothing
    /// else; the panel checks on opening whether the entry is the profile's own.
    static func isFund(_ page: String) -> Bool {
        page.range(of: "^#fund=[0-9]{1,12}$", options: .regularExpression) != nil && page.count <= 18
    }

    /// whether a way button may open this place: a page of `pages` or an entry of Finden
    static func allowed(_ page: String) -> Bool { pages.contains(page) || isFund(page) }

    struct Button: Identifiable {
        let id = UUID()
        let label: String
        let send: String?
        let open: String?
        let focus: Bool
        let main: Bool
    }

    struct Card: Identifiable {
        let id = UUID()
        let title: String
        let buttons: [Button]
    }

    static func parse(_ raw: Any?) -> [Card] {
        var out: [Card] = []
        for item in (raw as? [Any] ?? []).prefix(maxCards) {
            guard let o = item as? [String: Any], let list = o["buttons"] as? [Any] else { continue }
            var buttons: [Button] = []
            for b in list.prefix(maxButtons) {
                guard let d = b as? [String: Any] else { continue }
                let label = short(d["label"])
                let send = short(d["send"])
                let page = d["open"] as? String
                let open = page.flatMap { allowed($0) ? $0 : nil }
                let focus = (d["focus"] as? Bool) == true
                if label.isEmpty || (send.isEmpty && open == nil && !focus) { continue }
                buttons.append(Button(label: label, send: send.isEmpty ? nil : send, open: send.isEmpty ? open : nil,
                                      focus: send.isEmpty && open == nil && focus, main: (d["main"] as? Bool) == true))
            }
            if !buttons.isEmpty { out.append(Card(title: short(o["title"], max: 60), buttons: buttons)) }
        }
        return out
    }

    static func short(_ v: Any?, max: Int = maxLabel) -> String {
        let s = (v as? String ?? "").unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }
        let t = String(String.UnicodeScalarView(s)).trimmingCharacters(in: .whitespaces)
        return String(t.prefix(max))
    }
}
