import SwiftUI

// ---------------------------------------------------------------- Finden (fund.py, plan such-index Stufe E)
/// One tag of an entry: its kind (kategorie, person, firma, ort, frei), its word, where it came from (hand: the
/// owner's own, regel, modell, dokument: the Steckbrief) and whether it is a point of the Wissenskarte. The words
/// come from the owner's data, so they are shown as plain text only (Text(verbatim:)), never as a link or command.
struct FundTag: Identifiable, Hashable {
    let typ: String
    let wert: String
    var herkunft = "hand"
    var knoten = false
    var id: String { typ + "|" + wert.lowercased() }

    static let typen = ["kategorie", "person", "firma", "ort", "frei"]

    init(typ: String, wert: String, herkunft: String = "hand", knoten: Bool = false) {
        self.typ = typ
        self.wert = wert
        self.herkunft = herkunft
        self.knoten = knoten
    }

    init?(_ d: [String: Any]) {
        guard let t = d["typ"] as? String, Self.typen.contains(t), let w = d["wert"] as? String, !w.isEmpty else { return nil }
        self.init(typ: t, wert: String(w.prefix(60)), herkunft: d["herkunft"] as? String ?? "", knoten: d["knoten"] as? Bool ?? false)
    }

    /// what goes back to the Spark: only kind and word (it checks both by its fixed rules)
    var body: [String: String] { ["typ": typ, "wert": wert] }

    static func typName(_ t: String) -> String {
        switch t {
        case "kategorie": return String(localized: "Kategorie")
        case "person": return String(localized: "Person")
        case "firma": return String(localized: "Firma")
        case "ort": return String(localized: "Ort")
        default: return String(localized: "Schlagwort")
        }
    }

    var von: String {
        switch herkunft {
        case "hand": return String(localized: "von dir")
        case "modell": return String(localized: "vom Modell")
        case "dokument": return String(localized: "Steckbrief")
        default: return String(localized: "Regel")
        }
    }
}

/// One hit of the search: the entry's number, its source, title, date, the sender and the attachments that matched.
struct FundHit: Identifiable, Hashable {
    let id: Int
    let quelle: String
    let titel: String
    let wann: Date?
    let absender: String
    let anhaenge: [String]
    let tags: [FundTag]

    init?(_ d: [String: Any]) {
        guard let n = (d["id"] as? NSNumber)?.intValue, n > 0 else { return nil }
        id = n
        quelle = String((d["quelle"] as? String ?? "").prefix(20))
        titel = String((d["titel"] as? String ?? "").prefix(200))
        let t = (d["wann"] as? NSNumber)?.doubleValue ?? 0
        wann = t > 0 ? Date(timeIntervalSince1970: t) : nil
        let f = d["felder"] as? [String: Any] ?? [:]
        absender = String((f["absender"] as? String ?? "").prefix(120))
        anhaenge = (d["anhaenge"] as? [[String: Any]] ?? []).prefix(5).compactMap { $0["titel"] as? String }.map { String($0.prefix(120)) }
        tags = (d["tags"] as? [[String: Any]] ?? []).prefix(12).compactMap { FundTag($0) }
    }
}

/// A source of the index with its number of entries and how fresh it is (the tab Einstellungen of the page).
struct FundQuelle: Identifiable, Hashable {
    let id: String
    let de: String
    let en: String
    let an: Bool
    let n: Int
    let stand: String

    init?(_ d: [String: Any]) {
        guard let name = d["name"] as? String, name.range(of: "^[a-z]{2,20}$", options: .regularExpression) != nil else { return nil }
        id = name
        de = String((d["de"] as? String ?? name).prefix(40))
        en = String((d["en"] as? String ?? name).prefix(40))
        an = d["an"] as? Bool ?? false
        n = (d["n"] as? NSNumber)?.intValue ?? 0
        stand = String((d["stand"] as? String ?? "").prefix(60))
    }
}

/// One field of an entry: its fixed key and its value as text.
struct FundFeld: Hashable {
    let k: String
    let v: String
}

/// An attachment of a mail (its own entry in the index).
struct FundAnhang: Identifiable, Hashable {
    let id: Int
    let titel: String
}

/// One entry with every field, the origin of each tag, what the owner removed for good and a mail's attachments.
struct FundEintrag {
    let id: Int
    let quelle: String
    let titel: String
    let wann: Date?
    let auszug: String
    let felder: [FundFeld]
    let tags: [FundTag]
    let minus: [FundTag]
    let anhaenge: [FundAnhang]

    /// the fields in a fixed order (the same as the panel's page)
    static let feldOrder = ["absender", "an", "betrag", "nr", "datum", "name", "kb", "ort", "kalender", "firma", "kanal",
                            "fragen", "offen", "erledigt"]

    init?(_ d: [String: Any]) {
        guard let n = (d["id"] as? NSNumber)?.intValue, n > 0 else { return nil }
        id = n
        quelle = String((d["quelle"] as? String ?? "").prefix(20))
        titel = String((d["titel"] as? String ?? "").prefix(300))
        let t = (d["wann"] as? NSNumber)?.doubleValue ?? 0
        wann = t > 0 ? Date(timeIntervalSince1970: t) : nil
        auszug = String((d["auszug"] as? String ?? "").prefix(600))
        let f = d["felder"] as? [String: Any] ?? [:]
        felder = Self.feldOrder.compactMap { k -> FundFeld? in
            let v: String
            if let s = f[k] as? String { v = s } else if let x = f[k] as? NSNumber { v = x.stringValue }
            else if let l = f[k] as? [String] { v = l.joined(separator: ", ") } else { return nil }
            return v.isEmpty ? nil : FundFeld(k: k, v: String(v.prefix(200)))
        }
        tags = (d["tags"] as? [[String: Any]] ?? []).prefix(40).compactMap { FundTag($0) }
        minus = (d["minus"] as? [[String: Any]] ?? []).prefix(40).compactMap { x -> FundTag? in
            guard let t = x["typ"] as? String, FundTag.typen.contains(t), let w = x["wert"] as? String, !w.isEmpty else { return nil }
            return FundTag(typ: t, wert: String(w.prefix(60)))
        }
        anhaenge = (d["anhaenge"] as? [[String: Any]] ?? []).prefix(20).compactMap { a -> FundAnhang? in
            guard let n = (a["id"] as? NSNumber)?.intValue, n > 0 else { return nil }
            return FundAnhang(id: n, titel: String((a["titel"] as? String ?? "").prefix(120)))
        }
    }

    static func feldName(_ k: String) -> String {
        switch k {
        case "absender": return String(localized: "Absender")
        case "an": return String(localized: "An")
        case "betrag": return String(localized: "Betrag")
        case "nr": return String(localized: "Nummer")
        case "datum": return String(localized: "Datum")
        case "name": return String(localized: "Datei")
        case "kb": return String(localized: "Größe (KB)")
        case "ort": return String(localized: "Ort")
        case "kalender": return String(localized: "Kalender")
        case "firma": return String(localized: "Firma")
        case "kanal": return String(localized: "Kanal")
        case "fragen": return String(localized: "Fragen")
        case "offen": return String(localized: "Offen")
        default: return String(localized: "Erledigt")
        }
    }
}

/// Finden in the app: the same endpoints as the panel's page (iphone.THINGS "fund"), only while the admin released
/// Finden for the profile; the Spark checks every search, entry and tag again (its sources, the own mailboxes,
/// the fixed tag rules). Nothing of the index is kept on the iPhone.
@MainActor
final class FindenModel: ObservableObject {
    @Published var hits: [FundHit] = []
    @Published var searched = false
    @Published var deutung = ""
    @Published var quellen: [FundQuelle] = []
    @Published var kategorien: [String] = []
    @Published var eintraege = 0
    @Published var rest = 0
    @Published var laeuft = false
    @Published var quelle = ""
    @Published var kategorie = ""
    /// the period chip: "" any time, "30" the last 30 days, "jahr" this year, "vorjahr" last year
    @Published var zeit = ""
    @Published var loading = false
    @Published var error: String?
    private var seq = 0

    static var de: Bool { Locale.current.language.languageCode?.identifier == "de" }

    func sourceName(_ name: String) -> String {
        guard let q = quellen.first(where: { $0.id == name }) else { return name }
        return Self.de ? q.de : q.en
    }

    func loadState() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/fund/stand")
            quellen = (d["quellen"] as? [[String: Any]] ?? []).prefix(30).compactMap { FundQuelle($0) }
            kategorien = (d["kategorien"] as? [[String: Any]] ?? []).prefix(60).compactMap { $0["wert"] as? String }
            eintraege = (d["eintraege"] as? NSNumber)?.intValue ?? 0
            rest = ((d["rueckstand"] as? NSNumber)?.intValue ?? 0) + ((d["mail_rest"] as? NSNumber)?.intValue ?? 0)
            laeuft = d["laeuft"] as? Bool ?? false
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    /// from and to (YYYY-MM-DD) of the period chip, in the iPhone's calendar
    static func span(_ k: String, now: Date = Date()) -> (String, String)? {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = .current
        let f = DateFormatter()
        f.calendar = cal
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        let y = cal.component(.year, from: now)
        switch k {
        case "30":
            guard let a = cal.date(byAdding: .day, value: -30, to: now) else { return nil }
            return (f.string(from: a), f.string(from: now))
        case "jahr": return (String(y) + "-01-01", String(y) + "-12-31")
        case "vorjahr": return (String(y - 1) + "-01-01", String(y - 1) + "-12-31")
        default: return nil
        }
    }

    static func zeitName(_ k: String) -> String {
        switch k {
        case "30": return String(localized: "Letzte 30 Tage")
        case "jahr": return String(localized: "Dieses Jahr")
        case "vorjahr": return String(localized: "Letztes Jahr")
        default: return String(localized: "Zeitraum")
        }
    }

    func search(_ q: String) async {
        let words = String(q.trimmingCharacters(in: .whitespacesAndNewlines).prefix(200))
        seq += 1
        let mine = seq
        guard !words.isEmpty || !quelle.isEmpty || !kategorie.isEmpty || !zeit.isEmpty else {
            hits = []
            searched = false
            deutung = ""
            return
        }
        guard let api = SparkAPI.current else { return }
        var body: [String: Any] = ["worte": words]
        if !quelle.isEmpty { body["quelle"] = quelle }
        if !kategorie.isEmpty { body["kategorie"] = kategorie }
        if let s = Self.span(zeit) {
            body["von"] = s.0
            body["bis"] = s.1
        }
        loading = true
        defer { if mine == seq { loading = false } }
        do {
            let d = try await api.object("POST", "api/profile/fund/suche", body: body)
            guard mine == seq else { return }
            hits = (d["treffer"] as? [[String: Any]] ?? []).prefix(30).compactMap { FundHit($0) }
            deutung = Self.deutung(d["deutung"] as? [String: Any] ?? [:])
            searched = true
            error = nil
        } catch {
            if mine == seq { self.error = error.localizedDescription }
        }
    }

    /// what the Spark read from the typed words: a period and an appointment of the own calendar („vom OP“)
    static func deutung(_ d: [String: Any]) -> String {
        var p: [String] = []
        if let v = d["von"] as? String, !v.isEmpty {
            let b = d["bis"] as? String ?? ""
            p.append(String(localized: "Zeitraum") + ": " + v + " – " + (b.isEmpty ? String(localized: "heute") : b))
        }
        if let w = d["bezug"] as? String, !w.isEmpty {
            let t = (d["termin"] as? NSNumber)?.doubleValue ?? 0
            if t > 0 {
                p.append(String(localized: "Termin") + " „" + String(w.prefix(40)) + "“: "
                         + Date(timeIntervalSince1970: t).formatted(date: .abbreviated, time: .omitted))
            } else {
                p.append(String(localized: "Diesen Termin habe ich im Kalender nicht gefunden:") + " „" + String(w.prefix(40)) + "“")
            }
        }
        return p.joined(separator: " · ")
    }

    func entry(_ id: Int) async -> FundEintrag? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("GET", "api/profile/fund/eintrag/" + String(id))
            error = nil
            return FundEintrag(d)
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    /// the own tags of one entry, sent whole: what stays (plus) and what is gone for good (minus)
    func setTags(_ id: Int, plus: [[String: String]], minus: [[String: String]]) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            _ = try await api.object("PUT", "api/profile/fund/eintrag/" + String(id) + "/schlagworte", body: ["plus": plus, "minus": minus])
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func rebuild() async -> Int? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("POST", "api/profile/fund/neu", timeout: 300)
            error = nil
            await loadState()
            return (d["neu"] as? NSNumber)?.intValue ?? 0
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    func deleteIndex(own: Bool) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            _ = try await api.call("DELETE", "api/profile/fund", query: own ? ["hand": "true"] : [:])
            hits = []
            searched = false
            error = nil
            await loadState()
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }
}

/// A tag as a chip: an own one filled, one of the model with a dashed edge and „vom Modell“, a rule's grey; a point
/// of the Wissenskarte with a dot in the colour of its kind (like the panel's page).
struct FundChip: View {
    let tag: FundTag

    var body: some View {
        HStack(spacing: 3) {
            if tag.knoten { Circle().fill(WissenskarteModel.color(tag.typ)).frame(width: 6, height: 6) }
            Text(verbatim: tag.wert).lineLimit(1)
            if tag.herkunft == "modell" { Text("vom Modell").font(.caption2).foregroundStyle(.secondary) }
        }
        .font(.caption)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(tag.herkunft == "hand" ? Color.accentColor.opacity(0.2) : tag.herkunft == "modell" ? Color.clear : Color(.secondarySystemFill),
                    in: Capsule())
        .overlay {
            if tag.herkunft == "modell" {
                Capsule().strokeBorder(Color.secondary, style: StrokeStyle(lineWidth: 1, dash: [3, 2]))
            }
        }
    }
}

struct FundZeile: View {
    let hit: FundHit
    let source: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(verbatim: hit.titel.isEmpty ? "?" : hit.titel).lineLimit(2)
            HStack(spacing: 4) {
                Text(verbatim: source)
                if let w = hit.wann {
                    Text(verbatim: "·")
                    Text(w, format: .dateTime.day().month().year())
                }
                if !hit.absender.isEmpty { Text(verbatim: "· " + hit.absender).lineLimit(1) }
            }
            .font(.caption).foregroundStyle(.secondary)
            ForEach(Array(hit.anhaenge.enumerated()), id: \.offset) { _, a in
                Text(verbatim: String(localized: "Anhang:") + " " + a).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            if !hit.tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) { ForEach(hit.tags.prefix(6)) { FundChip(tag: $0) } }
                }
            }
        }
    }
}

/// Meine Sachen → Finden: a search over the own data with chips for source, category and period, the hits, a hit's
/// detail with its tags (✓ keeps one of the model or a rule as the own, × removes for good, + adds an own one),
/// „Original öffnen“ and a mail's attachments; the index's state, „Neu aufbauen“ and „Index löschen“ under
/// Einstellungen.
struct FindenView: View {
    var start = ""
    @StateObject private var m = FindenModel()
    @State private var q = ""
    @State private var wait: Task<Void, Never>?
    @State private var begun = false

    var body: some View {
        List {
            Section { chips }
            if !m.deutung.isEmpty { Text(verbatim: m.deutung).font(.caption).foregroundStyle(.secondary) }
            if m.searched && m.hits.isEmpty && !m.loading {
                Text("Nichts gefunden.").foregroundStyle(.secondary)
            } else if !m.searched && !m.loading {
                if m.eintraege > 0 {
                    Text("Gib Wörter ein oder wähle oben eine Quelle, eine Kategorie oder einen Zeitraum.").foregroundStyle(.secondary)
                } else {
                    Text("Der Index ist noch leer. Er füllt sich im Hintergrund, alle paar Minuten ein Stück.").foregroundStyle(.secondary)
                }
            }
            ForEach(m.hits) { h in
                NavigationLink { FundDetailView(id: h.id, model: m) } label: { FundZeile(hit: h, source: m.sourceName(h.quelle)) }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Finden")
        .searchable(text: $q, prompt: Text("Wörter, Firma, Person, Nummer …"))
        .onSubmit(of: .search) { run() }
        .onChange(of: q) { _, v in
            wait?.cancel()
            wait = Task {
                try? await Task.sleep(nanoseconds: 350_000_000)
                if Task.isCancelled { return }
                await m.search(v)
            }
        }
        .toolbar {
            NavigationLink { FundStandView(model: m) } label: { Label("Einstellungen", systemImage: "gearshape") }
        }
        .refreshable {
            await m.loadState()
            await m.search(q)
        }
        .overlay { if m.loading && m.hits.isEmpty { ProgressView() } }
        .task {
            guard !begun else { return }
            begun = true
            await m.loadState()
            if !start.isEmpty && q.isEmpty { q = String(start.prefix(200)) }
        }
    }

    private func run() {
        wait?.cancel()
        Task { await m.search(q) }
    }

    private var chips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Menu {
                    Button("Alle Quellen") { m.quelle = ""; run() }
                    ForEach(m.quellen.filter(\.an)) { s in
                        Button { m.quelle = s.id; run() } label: { Text(verbatim: m.sourceName(s.id)) }
                    }
                } label: { chip(m.quelle.isEmpty ? String(localized: "Quelle") : m.sourceName(m.quelle), on: !m.quelle.isEmpty) }
                Menu {
                    Button("Alle Kategorien") { m.kategorie = ""; run() }
                    ForEach(m.kategorien, id: \.self) { k in
                        Button { m.kategorie = k; run() } label: { Text(verbatim: k) }
                    }
                } label: { chip(m.kategorie.isEmpty ? String(localized: "Kategorie") : m.kategorie, on: !m.kategorie.isEmpty) }
                Menu {
                    Button("Jederzeit") { m.zeit = ""; run() }
                    ForEach(["30", "jahr", "vorjahr"], id: \.self) { k in
                        Button { m.zeit = k; run() } label: { Text(verbatim: FindenModel.zeitName(k)) }
                    }
                } label: { chip(FindenModel.zeitName(m.zeit), on: !m.zeit.isEmpty) }
            }
        }
        .listRowInsets(EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12))
    }

    private func chip(_ t: String, on: Bool) -> some View {
        HStack(spacing: 4) {
            Text(verbatim: t)
            Image(systemName: "chevron.down").font(.caption2)
        }
        .font(.subheadline)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(on ? Color.accentColor.opacity(0.18) : Color(.secondarySystemFill), in: Capsule())
        .foregroundStyle(on ? Color.accentColor : Color.primary)
    }
}

/// One entry: every field, the tags with where each came from and the buttons to keep, remove and add own ones.
struct FundDetailView: View {
    let id: Int
    @ObservedObject var model: FindenModel
    @State private var e: FundEintrag?
    @State private var loaded = false
    @State private var typ = "frei"
    @State private var neu = ""
    @State private var note: String?
    @State private var busy = false
    @State private var original: PanelPlace?

    var body: some View {
        List {
            if let e {
                Section {
                    Text(verbatim: e.titel.isEmpty ? "?" : e.titel).font(.headline)
                    HStack(spacing: 4) {
                        Text(verbatim: model.sourceName(e.quelle))
                        if let w = e.wann {
                            Text(verbatim: "·")
                            Text(w, format: .dateTime.day().month().year())
                        }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    ForEach(e.felder, id: \.k) { f in
                        LabeledContent { Text(verbatim: f.v) } label: { Text(verbatim: FundEintrag.feldName(f.k)) }
                    }
                    if !e.auszug.isEmpty { Text(verbatim: e.auszug).font(.callout).foregroundStyle(.secondary) }
                    if let url = SparkAPI.fundLink(e.id) {
                        Button { original = PanelPlace(url: url) } label: { Label("Original öffnen", systemImage: "arrow.up.forward.square") }
                    }
                }
                Section {
                    if e.tags.isEmpty { Text("Noch keine.").foregroundStyle(.secondary) }
                    ForEach(e.tags) { t in
                        HStack(spacing: 8) {
                            FundChip(tag: t)
                            Text(verbatim: FundTag.typName(t.typ) + " · " + t.von).font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            if t.herkunft != "hand" {
                                Button { Task { await keep(t) } } label: { Image(systemName: "checkmark") }
                                    .accessibilityLabel(Text("Behalten"))
                            }
                            Button(role: .destructive) { Task { await remove(t) } } label: { Image(systemName: "xmark") }
                                .accessibilityLabel(Text("Entfernen"))
                        }
                        .buttonStyle(.borderless)
                        .disabled(busy)
                    }
                } header: { Text("Schlagworte") } footer: {
                    Text("Deine Schlagworte gehen immer vor. ✓ übernimmt eines als deins, × entfernt es für immer.")
                }
                Section("Schlagwort hinzufügen") {
                    Picker("Art", selection: $typ) {
                        ForEach(FundTag.typen, id: \.self) { k in Text(verbatim: FundTag.typName(k)).tag(k) }
                    }
                    TextField("Neues Schlagwort", text: $neu)
                        .textInputAutocapitalization(.sentences)
                        .onSubmit { Task { await add() } }
                    Button("Hinzufügen") { Task { await add() } }
                        .disabled(busy || neu.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                if !e.minus.isEmpty {
                    Section {
                        Text(verbatim: e.minus.map(\.wert).joined(separator: ", ")).foregroundStyle(.secondary)
                    } header: { Text("Entfernt, kommt nicht wieder") }
                }
                if !e.anhaenge.isEmpty {
                    Section("Anhänge") {
                        ForEach(e.anhaenge) { a in Text(verbatim: a.titel.isEmpty ? "?" : a.titel) }
                    }
                }
            } else if loaded {
                Text("Diesen Eintrag gibt es nicht mehr.").foregroundStyle(.secondary)
            } else {
                LadeZeilen(rows: 4)
            }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let err = model.error { Text(SparkAPI.way(err)).foregroundStyle(.red) }
        }
        .navigationTitle("Eintrag")
        .navigationBarTitleDisplayMode(.inline)
        .task { await reload() }
        .sheet(item: $original) { p in PanelPage(url: p.url).ignoresSafeArea() }
    }

    private func reload() async {
        e = await model.entry(id)
        loaded = true
    }

    private func own(_ x: FundEintrag) -> ([[String: String]], [[String: String]]) {
        (x.tags.filter { $0.herkunft == "hand" }.map(\.body), x.minus.map(\.body))
    }

    private func keep(_ t: FundTag) async {
        guard let x = e else { return }
        var (plus, minus) = own(x)
        plus.append(t.body)
        await save(plus, minus)
    }

    private func remove(_ t: FundTag) async {
        guard let x = e else { return }
        var (plus, minus) = own(x)
        plus.removeAll { $0["typ"] == t.typ && $0["wert"] == t.wert }
        if t.herkunft != "hand" { minus.append(t.body) }
        await save(plus, minus)
    }

    private func add() async {
        let w = String(neu.trimmingCharacters(in: .whitespacesAndNewlines).prefix(60))
        guard let x = e, !w.isEmpty else { return }
        var (plus, minus) = own(x)
        minus.removeAll { $0["typ"] == typ && ($0["wert"] ?? "").lowercased() == w.lowercased() }
        plus.append(["typ": typ, "wert": w])
        neu = ""
        await save(plus, minus)
    }

    private func save(_ plus: [[String: String]], _ minus: [[String: String]]) async {
        busy = true
        defer { busy = false }
        if await model.setTags(id, plus: plus, minus: minus) {
            note = String(localized: "Gespeichert. Deine Schlagworte gehen vor.")
            await reload()
        }
    }
}

/// Finden → Einstellungen in the app: per source how many entries and how fresh, what is not read yet, „Neu
/// aufbauen“ and „Index löschen“ (the own tags stay unless chosen too).
struct FundStandView: View {
    @ObservedObject var model: FindenModel
    @State private var asking = false
    @State private var note: String?
    @State private var busy = false

    var body: some View {
        List {
            Section {
                ForEach(model.quellen) { q in
                    LabeledContent {
                        Text(verbatim: String(q.n) + (q.stand.isEmpty ? "" : " · " + q.stand))
                    } label: {
                        Text(verbatim: FindenModel.de ? q.de : q.en).foregroundStyle(q.an ? .primary : .secondary)
                    }
                }
                LabeledContent { Text(verbatim: String(model.rest)) } label: { Text("Noch nicht eingelesen") }
            } header: { Text("Suchindex") } footer: {
                Text("Mails, Anhänge, Termine und Kontakte liegen im Index versiegelt, ihre Wörter nur als Marken. Grau: nicht freigegeben.")
            }
            Section {
                Button {
                    Task {
                        busy = true
                        defer { busy = false }
                        if let n = await model.rebuild() {
                            note = String(localized: "Neu aufgebaut. Deine Schlagworte bleiben.") + " " + String(n)
                        }
                    }
                } label: {
                    if model.laeuft { Text("Läuft …") } else { Text("Neu aufbauen") }
                }
                .disabled(busy || model.laeuft)
                Button("Index löschen", role: .destructive) { asking = true }.disabled(busy)
            }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let err = model.error { Text(SparkAPI.way(err)).foregroundStyle(.red) }
        }
        .navigationTitle("Einstellungen")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.loadState() }
        .refreshable { await model.loadState() }
        .confirmationDialog("Den Suchindex löschen? Er baut sich danach von selbst neu auf.", isPresented: $asking, titleVisibility: .visible) {
            Button("Löschen, eigene Schlagworte behalten", role: .destructive) { Task { await delete(own: false) } }
            Button("Alles löschen, auch eigene Schlagworte", role: .destructive) { Task { await delete(own: true) } }
        }
    }

    private func delete(own: Bool) async {
        busy = true
        defer { busy = false }
        if await model.deleteIndex(own: own) { note = String(localized: "Gelöscht.") }
    }
}

/// The card under an answer that searched the own data (fund_suche): „In Finden ansehen“ with its words, and for the
/// Sofort-Karte (one hit clearly ahead) „Original öffnen“, the panel inside the app at #fund=<number>.
struct FundKarte: View {
    let q: String
    let id: Int?
    @State private var open: PanelPlace?
    @State private var finden = false

    var body: some View {
        HStack(spacing: 14) {
            if let id, let url = SparkAPI.fundLink(id) {
                Button { open = PanelPlace(url: url) } label: { Label("Original öffnen", systemImage: "arrow.up.forward.square") }
            }
            Button { finden = true } label: { Label("In Finden ansehen", systemImage: "magnifyingglass") }
            Spacer()
        }
        .buttonStyle(.borderless)
        .font(.footnote)
        .padding(.leading, 6)
        .sheet(item: $open) { p in PanelPage(url: p.url).ignoresSafeArea() }
        .sheet(isPresented: $finden) {
            NavigationStack {
                FindenView(start: q)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { finden = false } } }
            }
        }
    }
}
