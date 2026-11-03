import AppKit
import SwiftUI

/// Part "offen" (Begleiter Paket B): in the tab Heute the number of open Vorgänge and the first three cards with their
/// fixed buttons (GET /api/desk/offen). A button runs on the Spark through vorgaenge.act (POST /api/desk/offen/act),
/// which checks it like the card's own; only the direct buttons come (never a yes), the Mac decides nothing.
/// A card without a button opens Offen in the panel (#me=vgbox).
@MainActor
final class OffenCenter: ObservableObject {
    static let shared = OffenCenter()

    struct Act: Equatable {
        let k: String
        let de: String
    }

    struct Card: Equatable, Identifiable {
        let id: String
        let rev: Int
        let art: String
        let titel: String
        let zeile: String
        let acts: [Act]
    }

    @Published private(set) var n = 0
    @Published private(set) var cards: [Card] = []
    @Published private(set) var problem = ""
    @Published private(set) var said = ""
    @Published private(set) var loaded = false
    @Published private(set) var busy = false

    private var timer: Timer?
    private var active = false
    private var loading = false
    private var lastLoad: Date?

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: PostCenter.interval, repeats: true) { _ in
                Task { @MainActor in await OffenCenter.shared.refresh() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            Task { await refresh() }
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            n = 0
            cards = []
            loaded = false
            problem = ""
            said = ""
        }
    }

    func refreshSoon() {
        guard active else { return }
        if let l = lastLoad, Date().timeIntervalSince(l) < 60 { return }
        Task { await refresh() }
    }

    func refresh() async {
        guard active, !loading, let client = AppModel.shared.client, AppModel.shared.part("offen") else { return }
        loading = true
        defer { loading = false }
        do {
            let d = try await client.get("api/desk/offen", timeout: 30)
            guard active else { return }
            take(d)
            problem = ""
            lastLoad = Date()
        } catch is CancellationError {
        } catch {
            problem = AppModel.shared.absorb(error)
        }
    }

    /// one fixed button of a card; the answer carries the new list
    func act(_ card: Card, _ k: String) {
        guard !busy, card.acts.contains(where: { $0.k == k }), let client = AppModel.shared.client else { return }
        busy = true
        Task { @MainActor in
            defer { busy = false }
            do {
                let d = try await client.postJSON("api/desk/offen/act", ["id": card.id, "act": k, "rev": card.rev], timeout: 30)
                take(d)
                let t = DeskConfig.plain(d["text"] as? String ?? "", max: 240)
                said = t.isEmpty ? "Erledigt." : t
                HUD.show(said, symbol: "checkmark.circle")
            } catch {
                said = AppModel.shared.absorb(error)
                await refresh()
            }
        }
    }

    private func take(_ d: [String: Any]) {
        let r = Self.parse(d)
        n = r.n
        cards = r.cards
        loaded = true
    }

    /// GET /api/desk/offen, every value checked: at most 3 cards with at most 4 buttons each
    static func parse(_ d: [String: Any]) -> (n: Int, cards: [Card]) {
        let n = (d["n"] as? NSNumber).map { max(0, min($0.intValue, 99_999)) } ?? 0
        let cards = (d["cards"] as? [Any] ?? []).prefix(3).compactMap { x -> Card? in
            guard let c = x as? [String: Any], let id = c["id"] as? String, (1...40).contains(id.count),
                  id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "-") }),
                  let rev = (c["rev"] as? NSNumber)?.intValue else { return nil }
            let acts = (c["acts"] as? [Any] ?? []).prefix(4).compactMap { y -> Act? in
                guard let a = y as? [String: Any], let k = a["k"] as? String, (1...20).contains(k.count),
                      k.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_") }) else { return nil }
                let de = PlainText.line(a["de"], max: 30)
                return de.isEmpty ? nil : Act(k: k, de: de)
            }
            return Card(id: id, rev: rev, art: PlainText.line(c["art"], max: 40), titel: PlainText.line(c["titel"], max: 120),
                        zeile: PlainText.line(c["zeile"], max: 160), acts: acts)
        }
        return (n, cards)
    }
}

/// Part "find" (Begleiter Paket B): ⌃⌥F, the tile "Finden" or the menu opens a search field; the Spark searches the
/// profile's own index (POST /api/desk/fund) and gives title, source and date. A hit opens the entry in the panel
/// (#fund=<id>), "In Finden ansehen" the page Finden with this search (#fundq=<words>). Nothing stays on the Mac.
@MainActor
final class FindController: ObservableObject {
    static let shared = FindController()
    static let windowID = "find"
    static let maxText = 200

    struct Hit: Equatable, Identifiable {
        let id: Int
        let titel: String
        let quelle: String
        let wann: Int
    }

    @Published var line = ""
    @Published private(set) var hits: [Hit] = []
    @Published private(set) var status = "Wörter eingeben, dann Return."
    @Published private(set) var error = false
    @Published private(set) var busy = false
    @Published var focusTick = 0

    private var seq = 0

    static func open(fromHotkey: Bool) {
        guard AppModel.shared.paired, AppModel.shared.part("find") else {
            return HUD.show(AppModel.offHint("Finden"))
        }
        Task { @MainActor in
            let marked = fromHotkey ? (await Clip.copySelection() ?? "") : ""
            let c = shared
            c.reset(DeskConfig.plain(marked, max: maxText))
            Windows.shared.show(windowID, title: "Finden", size: NSSize(width: 460, height: 340), floating: true) {
                FindView(c: c)
            }
            c.focusTick += 1
        }
    }

    private func reset(_ text: String) {
        hits = []
        error = false
        status = "Wörter eingeben, dann Return."
        line = text
        if !text.isEmpty { search() }
    }

    private var words: String {
        String(line.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxText))
    }

    func search() {
        let w = words
        guard !w.isEmpty, let client = AppModel.shared.client else { return }
        seq += 1
        let mine = seq
        busy = true
        status = "Sucht …"
        Task { @MainActor in
            defer { if mine == seq { busy = false } }
            do {
                let d = try await client.postJSON("api/desk/fund", ["worte": w], timeout: 30)
                guard mine == seq else { return }
                hits = Self.parse(d)
                status = hits.isEmpty ? "Nichts gefunden." : hits.count == 1 ? "1 Treffer" : "\(hits.count) Treffer"
                error = false
            } catch {
                guard mine == seq else { return }
                hits = []
                status = AppModel.shared.absorb(error)
                self.error = true
            }
        }
    }

    func open(_ h: Hit) {
        AppModel.shared.openPanel("#fund=\(h.id)")
        Windows.shared.close(Self.windowID)
    }

    /// the page Finden in the panel with the same words
    func openAll() {
        let w = words
        guard !w.isEmpty, let q = w.addingPercentEncoding(withAllowedCharacters: .alphanumerics) else { return }
        AppModel.shared.openPanel("#fundq=" + q)
        Windows.shared.close(Self.windowID)
    }

    /// POST /api/desk/fund, every value checked: at most 8 hits
    static func parse(_ d: [String: Any]) -> [Hit] {
        (d["treffer"] as? [Any] ?? []).prefix(8).compactMap { x -> Hit? in
            guard let h = x as? [String: Any], let id = (h["id"] as? NSNumber)?.intValue, (1...999_999_999_999).contains(id)
            else { return nil }
            let wann = (h["wann"] as? NSNumber)?.intValue ?? 0
            return Hit(id: id, titel: PlainText.line(h["titel"], max: 120), quelle: PlainText.line(h["quelle"], max: 40),
                       wann: max(0, wann))
        }
    }

    static func day(_ wann: Int) -> String {
        guard wann > 0 else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "d.M.yyyy"
        return f.string(from: Date(timeIntervalSince1970: TimeInterval(wann)))
    }
}

struct FindView: View {
    @ObservedObject var c: FindController
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(verbatim: "Finden")
                .font(.system(size: 15, weight: .semibold))
            TextField("z. B. Rechnung Stadtwerke", text: $c.line)
                .textFieldStyle(.roundedBorder)
                .focused($focused)
                .onSubmit { c.search() }
            Text(verbatim: c.status)
                .font(.system(size: 12))
                .foregroundColor(c.error ? Theme.bad : Theme.muted)
            if !c.hits.isEmpty {
                ScrollView {
                    PanelBox {
                        ForEach(Array(c.hits.enumerated()), id: \.element.id) { i, h in
                            if i > 0 { RowLine() }
                            PanelRow(title: h.titel.isEmpty ? "Ohne Titel" : h.titel,
                                     detail: [h.quelle, FindController.day(h.wann)].filter { !$0.isEmpty }.joined(separator: " · "),
                                     symbol: "doc.text.magnifyingglass", verb: "Öffnen") { c.open(h) }
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
            HStack(spacing: 8) {
                Spacer()
                Button("Schließen") { Windows.shared.close(FindController.windowID) }
                    .buttonStyle(SoftButtonStyle())
                    .keyboardShortcut(.cancelAction)
                Button("In Finden ansehen") { c.openAll() }
                    .buttonStyle(SoftButtonStyle())
                    .disabled(c.line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Suchen") { c.search() }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(c.busy || c.line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(16)
        .frame(width: 460)
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .onChange(of: c.focusTick) { _ in focused = true }
        .onAppear { focused = true }
    }
}
