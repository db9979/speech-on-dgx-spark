import SwiftUI

// ---------------------------------------------------------------- Wissenskarte (wissenskarte.py, plan wissensgraph Stufe 1)
/// A point of the map: a page of the knowledge book, or (Stufe 2, "Personen, Firmen und Fristen") a person, company,
/// place, contract, account or deadline from the documents ("k" and its number, ent its kind). Titles come from the
/// owner's documents, so they are shown as plain text only (Text(verbatim:)), never as a link or a command.
struct WkPoint: Identifiable, Hashable {
    let id: String
    let title: String
    let kind: String
    let degree: Int
    var ent: String = ""
    var places: Int = 0
    /// sentences of its page in the knowledge book marked as a contradiction (red border)
    var contradictions: Int = 0
}

/// A topic island of the map (a fixed rule of the Spark groups closely connected points), with its point count.
struct WkIsland: Identifiable, Hashable {
    let id: String
    let name: String
    let count: Int
}

/// A document on the Zeitleiste: its date, its deadline and how many shown connections stand on it.
struct WkDated: Identifiable, Hashable {
    let id: String
    let name: String
    let date: String
    let deadline: String
    var count = 0
}

/// A document still waiting for the map; "Zuerst einarbeiten" puts it first (wissenskarte.vorziehen, daily limits stay).
struct WkWait: Identifiable, Hashable {
    let id: String
    let name: String
    let first: Bool
    let failed: Bool
}

/// A kind of points from documents and how many the profile has (numbers from the Spark, never names).
struct WkKind: Identifiable, Hashable {
    let id: String
    let count: Int
}

/// A suggestion of the Spark's fixed rules (wissensdoppelt.py): two points of one kind that may be the same; b would go
/// into a. Only "Verschieden" is done here, merging stays in the browser (the code of „Bestätigen“ there).
struct WkPair: Identifiable, Hashable {
    let a: Int
    let b: Int
    let nameA: String
    let nameB: String
    let kind: String
    let reason: String
    var id: String { String(a) + "-" + String(b) }
}

/// A connection the panel checked by its fixed rules, with the document and the page it stands on.
struct WkLine: Identifiable, Hashable {
    let id: Int
    let a: String
    let b: String
    let kind: String
    let cause: Bool
    let detail: String
    let source: String
    let page: Int?
    var doc: String = ""
    /// the date of its document (Steckbrief, else the day it came) and the document's deadline, YYYY-MM-DD or ""
    var date: String = ""
    var deadline: String = ""
}

/// Wissensbuch → Karte in the app: the part of the map the Spark chose (around a page or the best connected ones),
/// drawn here with own code from names and kinds, never from a picture or diagram code of the model. Only while the
/// admin released the Wissenskarte for the profile; the Spark checks every change (iphone.THINGS "wissenskarte").
@MainActor
final class WissenskarteModel: ObservableObject {
    @Published var points: [WkPoint] = []
    @Published var lines: [WkLine] = []
    @Published var center = ""
    @Published var cut = false
    @Published var waiting = 0
    @Published var waitList: [WkWait] = []
    /// points pinned in the browser (wk_lage); the phone keeps its ring layout, shows a pin and can loosen them
    @Published var pinned: Set<String> = []
    /// „Neu seit …“: only connections of the last 7 or 30 days (0 all), the days the Spark offers
    @Published var neu = 0
    @Published var neuTage: [Int] = []
    /// Themen-Inseln: the island shown ("" none) and the biggest islands for the menu
    @Published var island = ""
    @Published var islands: [WkIsland] = []
    @Published var loading = true
    @Published var error: String?
    /// the kind of points from documents shown with their neighbours ("" all), and how many there are of each kind
    @Published var only = ""
    @Published var kinds: [WkKind] = []
    /// kind → (German, English) words of the fixed list the Spark sends along
    var words: [String: (String, String)] = [:]
    var entWords: [String: (String, String)] = [:]
    /// „Vielleicht doppelt“: the open suggestions (at most the first 50) and how many are open
    @Published var pairs: [WkPair] = []
    @Published var pairsOpen = 0

    /// A point from documents: "k" and its number (never a page: those are 12 of 0-9a-f).
    static func isPoint(_ s: String) -> Bool {
        s.range(of: #"^k[1-9][0-9]{0,11}$"#, options: .regularExpression) != nil
    }

    static func isNode(_ s: String) -> Bool { WissensbuchModel.isPage(s) || isPoint(s) }

    func entWord(_ kind: String) -> String {
        guard let w = entWords[kind] else { return kind }
        return Locale.current.language.languageCode?.identifier == "de" ? w.0 : w.1
    }

    /// The border of a point: the centre in the accent colour, a point from documents in the colour of its kind.
    func edge(_ p: WkPoint) -> Color {
        if p.contradictions > 0 { return Theme.bad }
        if p.id == center { return Color.accentColor }
        return p.ent.isEmpty ? Color.secondary.opacity(0.5) : Self.color(p.ent)
    }

    /// The colour of a kind of point from documents (the same as in the panel); pages keep the plain look.
    static func color(_ ent: String) -> Color {
        switch ent {
        case "person": return Theme.wkPerson
        case "firma": return Theme.wkFirma
        case "ort": return Theme.wkOrt
        case "vertrag": return Theme.wkVertrag
        case "konto": return Theme.wkKonto
        case "frist": return Theme.wkFrist
        default: return Color.secondary
        }
    }

    func word(_ kind: String) -> String {
        guard let w = words[kind] else { return kind }
        return Locale.current.language.languageCode?.identifier == "de" ? w.0 : w.1
    }

    func load(_ around: String = "", only kind: String = "") async {
        guard let api = SparkAPI.current else { return }
        if Self.isNode(around) || !kind.isEmpty { island = "" }
        var q = Self.isNode(around) ? ["um": around] : (kind.isEmpty ? [:] : ["art": kind])
        if q.isEmpty && Self.isNode(island) { q["insel"] = island } else { q["inseln"] = "0" }
        if neu > 0 { q["neu"] = String(neu) }
        do {
            let d = try await api.object("GET", "api/profile/wissenskarte", query: q)
            points = (d["nodes"] as? [[String: Any]] ?? []).prefix(150).compactMap { n in
                guard let id = n["id"] as? String, Self.isNode(id) else { return nil }
                return WkPoint(id: id, title: String((n["title"] as? String ?? "").prefix(80)), kind: n["art"] as? String ?? "Thema",
                               degree: (n["deg"] as? NSNumber)?.intValue ?? 0, ent: Self.isPoint(id) ? (n["ent"] as? String ?? "") : "",
                               places: (n["n"] as? NSNumber)?.intValue ?? 0, contradictions: (n["w"] as? NSNumber)?.intValue ?? 0)
            }
            only = d["art"] as? String ?? ""
            entWords = [:]
            for (k, v) in d["ent_arten"] as? [String: [Any]] ?? [:] where v.count >= 2 {
                entWords[k] = (v[0] as? String ?? k, v[1] as? String ?? k)
            }
            let counts = d["knoten"] as? [String: Any] ?? [:]
            kinds = ["person", "firma", "ort", "vertrag", "konto", "frist"].compactMap { k in
                let n = (counts[k] as? NSNumber)?.intValue ?? 0
                return n > 0 ? WkKind(id: k, count: n) : nil
            }
            let known = Set(points.map(\.id))
            lines = (d["edges"] as? [[String: Any]] ?? []).prefix(400).compactMap { e in
                guard let id = (e["id"] as? NSNumber)?.intValue, let a = e["a"] as? String, let b = e["b"] as? String,
                      known.contains(a), known.contains(b) else { return nil }
                let p = (e["page"] as? NSNumber)?.intValue ?? 0
                return WkLine(id: id, a: a, b: b, kind: e["art"] as? String ?? "", cause: e["cause"] as? Bool ?? false,
                              detail: String((e["detail"] as? String ?? "").prefix(40)),
                              source: String((e["name"] as? String ?? "").prefix(120)), page: p > 0 ? p : nil,
                              doc: Self.day(e["doc"] as? String ?? "", pattern: #"^[0-9a-f]{12}$"#),
                              date: Self.day(e["datum"] as? String ?? ""), deadline: Self.day(e["frist"] as? String ?? ""))
            }
            words = [:]
            for (k, v) in d["arten"] as? [String: [Any]] ?? [:] where v.count >= 2 {
                words[k] = (v[0] as? String ?? k, v[1] as? String ?? k)
            }
            center = d["um"] as? String ?? ""
            cut = d["cut"] as? Bool ?? false
            waiting = (d["warten_n"] as? NSNumber ?? d["wait"] as? NSNumber)?.intValue ?? 0
            neuTage = ((d["zeit"] as? [String: Any])?["neu_tage"] as? [NSNumber] ?? []).map(\.intValue).filter { $0 > 0 && $0 < 1000 }
            let ins = d["inseln"] as? [String: Any] ?? [:]
            if (ins["anzahl"] as? NSNumber)?.intValue ?? 0 > 1 { await loadIslands() } else { islands = [] }
            pinned = Set((d["lage"] as? [String: Any] ?? [:]).keys.filter { Self.isNode($0) })
            waitList = (d["warten"] as? [[String: Any]] ?? []).prefix(12).compactMap { w in
                guard let id = w["id"] as? String, WissensbuchModel.isPage(id) else { return nil }
                return WkWait(id: id, name: String((w["name"] as? String ?? "").prefix(120)), first: w["vor"] as? Bool ?? false,
                              failed: w["fehler"] as? Bool ?? false)
            }
            error = nil
            if d["ents"] as? Bool ?? false { await loadPairs() } else { pairs = []; pairsOpen = 0 }
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    /// The open suggestions of the Spark's fixed rules; names are text from the documents, shown as plain text only.
    func loadPairs() async {
        guard let api = SparkAPI.current else { return }
        guard let d = try? await api.object("GET", "api/profile/wissenskarte/paare") else { return }
        pairs = (d["paare"] as? [[String: Any]] ?? []).prefix(50).compactMap { p in
            guard let a = p["a"] as? [String: Any], let b = p["b"] as? [String: Any],
                  let ia = (a["id"] as? NSNumber)?.intValue, let ib = (b["id"] as? NSNumber)?.intValue else { return nil }
            return WkPair(a: ia, b: ib, nameA: String((a["name"] as? String ?? "").prefix(80)),
                          nameB: String((b["name"] as? String ?? "").prefix(80)), kind: p["art"] as? String ?? "",
                          reason: p["grund"] as? String ?? "")
        }
        pairsOpen = (d["offen"] as? NSNumber)?.intValue ?? pairs.count
    }

    /// The words for the reason of a suggestion (the same fixed words as in the panel).
    static func reason(_ r: String) -> String {
        switch r {
        case "anrede": return String(localized: "mit Anrede oder Titel")
        case "reihenfolge": return String(localized: "Nachname zuerst")
        case "initiale": return String(localized: "mit Initiale")
        case "rechtsform": return String(localized: "andere Rechtsform")
        case "tippfehler": return String(localized: "fast gleich geschrieben")
        default: return String(localized: "andere Schreibweise")
        }
    }

    /// „Verschieden“: the two stay apart for good, the Spark never suggests or merges them again.
    func different(_ p: WkPair) async {
        guard let api = SparkAPI.current else { return }
        do { _ = try await api.object("POST", "api/profile/wissenskarte/paare/verschieden", body: ["a": p.a, "b": p.b]); error = nil }
        catch { self.error = error.localizedDescription }
        await loadPairs()
    }

    /// "Stimmt nicht": the connection goes and never comes back from that document.
    func first(_ w: WkWait) async {
        guard let api = SparkAPI.current else { return }
        do { _ = try await api.object("POST", "api/profile/wissenskarte/vorziehen/\(w.id)"); error = nil }
        catch { self.error = error.localizedDescription }
        await load(center, only: only)
    }

    /// The overview of the islands (?inseln=1): names and point counts only, the biggest first.
    func loadIslands() async {
        guard let api = SparkAPI.current,
              let d = try? await api.object("GET", "api/profile/wissenskarte", query: ["inseln": "1"]) else { return }
        islands = (((d["inseln"] as? [String: Any])?["liste"] as? [[String: Any]]) ?? []).prefix(80).compactMap { x in
            guard let id = x["id"] as? String, Self.isNode(id) else { return nil }
            return WkIsland(id: id, name: String((x["name"] as? String ?? "").prefix(80)), count: (x["n"] as? NSNumber)?.intValue ?? 0)
        }
    }

    /// A value only when it has the fixed form (a date YYYY-MM-DD by default), else "".
    static func day(_ s: String, pattern: String = #"^(19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}$"#) -> String {
        s.range(of: pattern, options: .regularExpression) != nil ? s : ""
    }

    /// Zeitleiste: the documents of the shown connections by their date, with their deadline and how many connections.
    var timeline: [WkDated] {
        var by: [String: WkDated] = [:]
        for l in lines where !l.doc.isEmpty && !l.date.isEmpty {
            var x = by[l.doc] ?? WkDated(id: l.doc, name: l.source, date: l.date, deadline: l.deadline)
            x.count += 1
            by[l.doc] = x
        }
        return by.values.sorted { $0.date == $1.date ? $0.name < $1.name : $0.date < $1.date }
    }

    /// „Lösen“: one point (or every one with "") goes back to the drawn layout of the browser.
    func unpin(_ id: String) async {
        guard let api = SparkAPI.current, id.isEmpty || Self.isNode(id) else { return }
        do { _ = try await api.object("DELETE", "api/profile/wissenskarte/lage" + (id.isEmpty ? "" : "/" + id)); error = nil }
        catch { self.error = error.localizedDescription }
        await load(center, only: only)
    }

    func wrong(_ line: WkLine) async {
        guard let api = SparkAPI.current else { return }
        do { _ = try await api.object("DELETE", "api/profile/wissenskarte/kante/\(line.id)"); error = nil }
        catch { self.error = error.localizedDescription }
        await load(center)
    }

    /// "Löschen" for a point from documents: only the owner's tap, with the code of „Bestätigen“ when the profile has
    /// the second step (SparkAPI.confirmed); it never comes back from the documents it stood in.
    func delete(_ point: WkPoint) async {
        guard let api = SparkAPI.current, Self.isPoint(point.id) else { return }
        do { _ = try await api.object("DELETE", "api/profile/wissenskarte/knoten/\(point.id.dropFirst())"); error = nil }
        catch { self.error = error.localizedDescription }
        await load(center == point.id ? "" : center, only: only)
    }

    /// Places by fixed rules: the centre (or the best connected point) in the middle, its neighbours on a ring around
    /// it, the rest on an outer ring; the same answer always gives the same picture.
    func places(in size: CGSize) -> [String: CGPoint] {
        guard !points.isEmpty else { return [:] }
        let mid = CGPoint(x: size.width / 2, y: size.height / 2)
        let first = points.first { $0.id == center } ?? points.max { $0.degree < $1.degree }!
        var near: Set<String> = []
        for l in lines {
            if l.a == first.id { near.insert(l.b) }
            if l.b == first.id { near.insert(l.a) }
        }
        let inner = points.filter { near.contains($0.id) }
        let outer = points.filter { $0.id != first.id && !near.contains($0.id) }
        let r: CGFloat = min(size.width, size.height) / 2 - 44
        var out = [first.id: mid]
        let rings: [(shift: CGFloat, list: [WkPoint], radius: CGFloat)] = [(0, inner, r * (outer.isEmpty ? 0.8 : 0.5)), (0.3, outer, r)]
        for ring in rings where !ring.list.isEmpty {
            for (i, p) in ring.list.enumerated() {
                // all in Double, so cos and sin have one meaning (Double and CGFloat both have them)
                let angle: Double = Double(i) / Double(ring.list.count) * 2 * Double.pi + Double(ring.shift) - Double.pi / 2
                let radius = Double(ring.radius)
                let x: Double = Double(mid.x) + radius * cos(angle)
                let y: Double = Double(mid.y) + radius * sin(angle)
                out[p.id] = CGPoint(x: x, y: y)
            }
        }
        return out
    }
}

struct WissenskarteView: View {
    var around = ""
    @StateObject private var m = WissenskarteModel()
    @State private var picked: WkPoint?
    @State private var showPairs = false
    @State private var showWaiting = false
    @State private var showTimeline = false

    var body: some View {
        VStack(spacing: 0) {
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText).padding() }
            if m.loading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if m.points.isEmpty {
                Text("Noch keine Verbindungen. Sie entstehen nur, wenn niemand mit dem Spark spricht.")
                    .foregroundStyle(.secondary).padding().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                GeometryReader { geo in
                    let at = m.places(in: geo.size)
                    ZStack {
                        Canvas { ctx, _ in
                            for l in m.lines {
                                guard let a = at[l.a], let b = at[l.b] else { continue }
                                var path = Path()
                                path.move(to: a)
                                path.addLine(to: b)
                                ctx.stroke(path, with: .color(l.cause ? Theme.bad : .secondary.opacity(0.6)),
                                           style: StrokeStyle(lineWidth: l.cause ? 2 : 1.2, dash: l.cause ? [6, 4] : []))
                            }
                        }
                        ForEach(m.points) { p in
                            if let pos = at[p.id] {
                                Button { picked = p } label: {
                                    (m.pinned.contains(p.id) ? Text(Image(systemName: "pin.fill")) + Text(verbatim: " " + p.title) : Text(verbatim: p.title))
                                        .font(.caption.weight(p.id == m.center ? .bold : .regular))
                                        .lineLimit(1).padding(.horizontal, 8).padding(.vertical, 5)
                                        .background(.background, in: Capsule())
                                        .overlay(Capsule().stroke(m.edge(p), lineWidth: p.id == m.center || !p.ent.isEmpty ? 2 : 1))
                                }
                                .buttonStyle(.plain).frame(maxWidth: 140).position(pos)
                            }
                        }
                    }
                }
                if m.cut { Text("Die Karte zeigt nur einen Teil. Tippe auf einen Punkt und dann „In die Mitte“.").font(.caption).foregroundStyle(.secondary).padding(8) }
            }
            if m.waiting > 0 {
                Button { showWaiting = true } label: {
                    Text(verbatim: String(localized: "Noch nicht eingearbeitet:") + " " + String(m.waiting))
                }
                .font(.caption).padding(8)
            }
            if m.pairsOpen > 0 {
                Button { showPairs = true } label: {
                    Text(verbatim: String(localized: "Vielleicht doppelt") + " · " + String(m.pairsOpen))
                }
                .font(.caption).padding(8)
            }
        }
        .navigationTitle("Wissenskarte")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !m.islands.isEmpty {
                Menu {
                    ForEach(m.islands) { x in
                        Button { m.island = x.id; Task { await m.load() } } label: {
                            Label(x.name + " · " + String(x.count), systemImage: m.island == x.id ? "checkmark" : "circle.hexagongrid")
                        }
                    }
                } label: { Label("Themen-Inseln", systemImage: "circle.hexagongrid") }
            }
            if !m.center.isEmpty || !m.only.isEmpty || !m.island.isEmpty {
                Button("Alles") { m.island = ""; Task { await m.load() } }
            }
            Menu {
                ForEach(m.neuTage, id: \.self) { n in
                    Button { m.neu = m.neu == n ? 0 : n; Task { await m.load(m.center, only: m.only) } } label: {
                        Label(n == 7 ? String(localized: "Neu seit letzter Woche") : String(localized: "Neu seit") + " " + String(n) + " " + String(localized: "Tagen"),
                              systemImage: m.neu == n ? "checkmark" : "clock")
                    }
                }
                if m.neu > 0 { Button("Alle Zeiten") { m.neu = 0; Task { await m.load(m.center, only: m.only) } } }
                Button { showTimeline = true } label: { Label("Zeitleiste", systemImage: "calendar.day.timeline.left") }
            } label: { Label("Zeit", systemImage: "clock") }
            if !m.kinds.isEmpty {
                Menu {
                    ForEach(m.kinds) { k in
                        Button { Task { await m.load(only: k.id) } } label: {
                            Text(verbatim: m.entWord(k.id) + " · " + String(k.count))
                        }
                    }
                } label: { Label("Nach Art", systemImage: "line.3.horizontal.decrease.circle") }
            }
        }
        .sheet(item: $picked) { p in
            WkPointSheet(point: p, model: m) { picked = nil }
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showTimeline) {
            WkTimelineSheet(model: m)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showWaiting) {
            WkWaitSheet(model: m)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showPairs) {
            WkPairsSheet(model: m)
                .presentationDetents([.medium, .large])
        }
        .refreshable { await m.load(m.center, only: m.only) }
        .task { await m.load(around) }
    }
}

/// The point tapped: its connections with their source, "In die Mitte" and "Stimmt nicht" per connection; a point from
/// documents also "Löschen" (renaming and merging stay in the browser, Wissensbuch → Karte).
struct WkPointSheet: View {
    let point: WkPoint
    @ObservedObject var model: WissenskarteModel
    let close: () -> Void
    @State private var asking = false

    var body: some View {
        NavigationStack {
            List {
                let mine = model.lines.filter { $0.a == point.id || $0.b == point.id }
                Section {
                    ForEach(mine) { l in
                        let other = model.points.first { $0.id == (l.a == point.id ? l.b : l.a) }?.title ?? ""
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: (l.a == point.id ? "" : other + " ") + model.word(l.kind) + (l.a == point.id ? " " + other : " " + point.title)
                                 + (l.detail.isEmpty ? "" : " · " + l.detail))
                                .foregroundStyle(l.cause ? Theme.bad : .primary)
                            Text(verbatim: l.page.map { l.source + " · " + String(localized: "S.") + " " + String($0) } ?? l.source)
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) { Task { await model.wrong(l) } } label: {
                                Label("Stimmt nicht", systemImage: "xmark")
                            }
                        }
                    }
                } header: { Text("Verbindungen") } footer: { Text("Nach links wischen: „Stimmt nicht“ entfernt die Verbindung für immer aus diesem Dokument.") }
                Section {
                    Button("In die Mitte") { close(); Task { await model.load(point.id) } }
                    if model.pinned.contains(point.id) {
                        Button("Lösen") { close(); Task { await model.unpin(point.id) } }
                    }
                } footer: {
                    if model.pinned.contains(point.id) { Text("Im Browser angeheftet: Dort bleibt der Punkt, wo er hingezogen wurde. „Lösen“ ordnet ihn wieder selbst ein.") }
                }
                if !point.ent.isEmpty {
                    let own = model.pairs.filter { "k" + String($0.a) == point.id || "k" + String($0.b) == point.id }
                    if !own.isEmpty {
                        Section {
                            ForEach(own) { p in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(verbatim: "k" + String(p.a) == point.id ? p.nameB : p.nameA)
                                    Text(verbatim: WissenskarteModel.reason(p.reason)).font(.caption).foregroundStyle(.secondary)
                                }
                                .swipeActions(edge: .trailing) {
                                    Button { Task { await model.different(p) } } label: { Label("Verschieden", systemImage: "xmark") }
                                }
                            }
                        } header: { Text("Vielleicht derselbe Punkt") } footer: { Text(SparkAPI.way(String(localized: "Nach links wischen: „Verschieden“, dann fragt der Spark nie wieder. Zusammenführen geht im Panel unter Wissensbuch → Karte."))) }
                    }
                    Section {
                        Text(verbatim: model.entWord(point.ent) + " · " + String(point.places) + " " + String(localized: "Stellen in Dokumenten"))
                            .foregroundStyle(WissenskarteModel.color(point.ent))
                        Button("Löschen", role: .destructive) { asking = true }
                    } footer: { Text(SparkAPI.way(String(localized: "Umbenennen und Zusammenführen gehen im Panel unter Wissensbuch → Karte."))) }
                }
            }
            .navigationTitle(Text(verbatim: point.title))
            .navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Diesen Punkt löschen? Aus diesen Dokumenten kommt er nicht wieder.", isPresented: $asking, titleVisibility: .visible) {
                Button("Löschen", role: .destructive) { close(); Task { await model.delete(point) } }
            }
        }
    }
}

/// „Vielleicht doppelt“: the open suggestions of the Spark's fixed rules; swipe for „Verschieden“ (never again), merging
/// stays in the browser with the code of „Bestätigen“ (Wissensbuch → Karte), as the hint below says.
struct WkPairsSheet: View {
    @ObservedObject var model: WissenskarteModel

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(model.pairs) { p in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: p.nameA + " · " + p.nameB)
                            Text(verbatim: model.entWord(p.kind) + " · " + WissenskarteModel.reason(p.reason))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        .swipeActions(edge: .trailing) {
                            Button { Task { await model.different(p) } } label: { Label("Verschieden", systemImage: "xmark") }
                        }
                    }
                } footer: { Text(SparkAPI.way(String(localized: "Nach links wischen: „Verschieden“, dann fragt der Spark nie wieder. Zusammenführen geht im Panel unter Wissensbuch → Karte."))) }
            }
            .navigationTitle("Vielleicht doppelt")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await model.loadPairs() }
        }
    }
}

/// The documents still waiting for the map; "Zuerst" puts one first (it goes next in quiet minutes, daily limits stay).
struct WkWaitSheet: View {
    @ObservedObject var model: WissenskarteModel

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(model.waitList) { w in
                        HStack {
                            Text(verbatim: w.name).lineLimit(2)
                            Spacer()
                            if w.failed {
                                Text("nicht eingearbeitet").font(.caption).foregroundStyle(Theme.badText)
                            } else if w.first {
                                Text("kommt zuerst").font(.caption).foregroundStyle(.secondary)
                            } else {
                                Button("Zuerst") { Task { await model.first(w) } }.buttonStyle(.bordered)
                            }
                        }
                    }
                } footer: { Text("„Zuerst“ arbeitet das Dokument als Nächstes ein, in ruhigen Minuten.") }
            }
            .navigationTitle("Wartet")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// Zeitleiste: the documents of the part shown, oldest first, each with its date, its deadline and its connections.
struct WkTimelineSheet: View {
    @ObservedObject var model: WissenskarteModel

    var body: some View {
        NavigationStack {
            List {
                let items = model.timeline
                if items.isEmpty { Text("Keine Verbindung mit Datum in diesem Ausschnitt.").foregroundStyle(.secondary) }
                ForEach(items) { x in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: x.date + " · " + x.name).lineLimit(2)
                        HStack(spacing: 8) {
                            Text(verbatim: String(localized: "Verbindungen") + ": " + String(x.count))
                            if !x.deadline.isEmpty {
                                Text(verbatim: String(localized: "Frist") + " " + x.deadline).foregroundStyle(Theme.badText)
                            }
                        }
                        .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Zeitleiste")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
