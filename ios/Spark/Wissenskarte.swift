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
}

/// A kind of points from documents and how many the profile has (numbers from the Spark, never names).
struct WkKind: Identifiable, Hashable {
    let id: String
    let count: Int
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
    @Published var loading = true
    @Published var error: String?
    /// the kind of points from documents shown with their neighbours ("" all), and how many there are of each kind
    @Published var only = ""
    @Published var kinds: [WkKind] = []
    /// kind → (German, English) words of the fixed list the Spark sends along
    var words: [String: (String, String)] = [:]
    var entWords: [String: (String, String)] = [:]

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
        if p.id == center { return Color.accentColor }
        return p.ent.isEmpty ? Color.secondary.opacity(0.5) : Self.color(p.ent)
    }

    /// The colour of a kind of point from documents (the same as in the panel); pages keep the plain look.
    static func color(_ ent: String) -> Color {
        switch ent {
        case "person": return .pink
        case "firma": return .blue
        case "ort": return .orange
        case "vertrag": return .purple
        case "konto": return .green
        case "frist": return .red
        default: return Color.secondary
        }
    }

    func word(_ kind: String) -> String {
        guard let w = words[kind] else { return kind }
        return Locale.current.language.languageCode?.identifier == "de" ? w.0 : w.1
    }

    func load(_ around: String = "", only kind: String = "") async {
        guard let api = SparkAPI.current else { return }
        let q = Self.isNode(around) ? ["um": around] : (kind.isEmpty ? [:] : ["art": kind])
        do {
            let d = try await api.object("GET", "api/profile/wissenskarte", query: q)
            points = (d["nodes"] as? [[String: Any]] ?? []).prefix(150).compactMap { n in
                guard let id = n["id"] as? String, Self.isNode(id) else { return nil }
                return WkPoint(id: id, title: String((n["title"] as? String ?? "").prefix(80)), kind: n["art"] as? String ?? "Thema",
                               degree: (n["deg"] as? NSNumber)?.intValue ?? 0, ent: Self.isPoint(id) ? (n["ent"] as? String ?? "") : "",
                               places: (n["n"] as? NSNumber)?.intValue ?? 0)
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
                              source: String((e["name"] as? String ?? "").prefix(120)), page: p > 0 ? p : nil)
            }
            words = [:]
            for (k, v) in d["arten"] as? [String: [Any]] ?? [:] where v.count >= 2 {
                words[k] = (v[0] as? String ?? k, v[1] as? String ?? k)
            }
            center = d["um"] as? String ?? ""
            cut = d["cut"] as? Bool ?? false
            waiting = (d["wait"] as? NSNumber)?.intValue ?? 0
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    /// "Stimmt nicht": the connection goes and never comes back from that document.
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

    var body: some View {
        VStack(spacing: 0) {
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red).padding() }
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
                                ctx.stroke(path, with: .color(l.cause ? .red : .secondary.opacity(0.6)),
                                           style: StrokeStyle(lineWidth: l.cause ? 2 : 1.2, dash: l.cause ? [6, 4] : []))
                            }
                        }
                        ForEach(m.points) { p in
                            if let pos = at[p.id] {
                                Button { picked = p } label: {
                                    Text(verbatim: p.title).font(.caption.weight(p.id == m.center ? .bold : .regular))
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
            if m.waiting > 0 { Text(verbatim: String(localized: "Noch nicht eingearbeitet:") + " " + String(m.waiting)).font(.caption).foregroundStyle(.secondary).padding(8) }
        }
        .navigationTitle("Wissenskarte")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !m.center.isEmpty || !m.only.isEmpty {
                Button("Alles") { Task { await m.load() } }
            }
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
                                .foregroundStyle(l.cause ? .red : .primary)
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
                }
                if !point.ent.isEmpty {
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
