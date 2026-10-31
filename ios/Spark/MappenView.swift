import SwiftUI

// ---------------------------------------------------------------- Mappen (mappen.py, plan open-notebook Push 1b)
/// One Mappe of the list: its id, the name and goal the person gave it and the number of entries.
struct MpMappe: Identifiable, Hashable {
    let id: String
    let name: String
    let ziel: String
    let n: Int

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, id.range(of: "^[0-9a-f]{12}$", options: .regularExpression) != nil else { return nil }
        self.id = id
        name = String((d["name"] as? String ?? "").prefix(60))
        ziel = String((d["ziel"] as? String ?? "").prefix(200))
        n = (d["n"] as? NSNumber)?.intValue ?? 0
    }
}

/// One entry of a Mappe: a document or a Wissensbuch page, its level (aus, kurz, ganz) and what the panel's fixed rule
/// makes of it (geht: kurz, ganz, suche, aus, voll). Titles are the documents' own words: plain text only.
struct MpEintrag: Identifiable, Hashable {
    let art: String
    let ref: String
    let titel: String
    let notiz: Bool
    var stufe: String
    let geht: String
    let grau: Bool
    let tokenKurz: Int
    let tokenGanz: Int
    var id: String { art + ":" + ref }

    static let stufen = ["aus", "kurz", "ganz"]

    init?(_ d: [String: Any]) {
        guard let a = d["art_eintrag"] as? String, ["dok", "seite"].contains(a),
              let r = d["ref"] as? String, r.range(of: "^[0-9a-zA-Z_-]{1,40}$", options: .regularExpression) != nil else { return nil }
        art = a
        ref = r
        titel = String((d["titel"] as? String ?? "").prefix(200))
        notiz = (d["quelle"] as? String) == "notiz"
        let s = d["stufe"] as? String ?? "kurz"
        stufe = Self.stufen.contains(s) ? s : "kurz"
        geht = String((d["geht"] as? String ?? "aus").prefix(10))
        grau = d["grau"] as? Bool ?? false
        let t = d["token"] as? [String: Any] ?? [:]
        tokenKurz = (t["kurz"] as? NSNumber)?.intValue ?? 0
        tokenGanz = (t["ganz"] as? NSNumber)?.intValue ?? 0
    }

    static func stufeName(_ s: String) -> String {
        switch s {
        case "aus": return String(localized: "aus")
        case "ganz": return String(localized: "ganz")
        default: return String(localized: "kurz")
        }
    }

    var gehtText: String {
        if grau { return String(localized: "Wissensbuch gesperrt: geht nicht mit") }
        switch geht {
        case "kurz": return String(localized: "geht kurz mit")
        case "ganz": return String(localized: "geht ganz mit")
        case "suche": return String(localized: "zu groß: nur die passenden Stellen")
        case "voll": return String(localized: "Budget voll: geht nicht mit")
        default: return String(localized: "geht nicht mit")
        }
    }
}

/// One Mappe with its entries and the count of what goes to the model with every question.
struct MpDetail {
    let id: String
    let name: String
    let ziel: String
    var eintraege: [MpEintrag]
    let token: Int
    let budget: Int

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String else { return nil }
        self.id = id
        name = String((d["name"] as? String ?? "").prefix(60))
        ziel = String((d["ziel"] as? String ?? "").prefix(200))
        eintraege = (d["eintraege"] as? [[String: Any]] ?? []).prefix(100).compactMap { MpEintrag($0) }
        token = (d["token"] as? NSNumber)?.intValue ?? 0
        budget = (d["budget"] as? NSNumber)?.intValue ?? 0
    }
}

/// Mappen in the app: the same endpoints as the panel's page (iphone.THINGS "mappen"), only while the admin released
/// Mappen for the profile. The Spark checks every change again (own Mappe, own entry, the fixed levels) and decides
/// with its fixed rule what goes to the model, never the app. Nothing of a Mappe is kept on the iPhone.
@MainActor
final class MappenModel: ObservableObject {
    @Published var list: [MpMappe] = []
    @Published var max = 50
    @Published var loaded = false
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        defer { loaded = true }
        do {
            let d = try await api.object("GET", "api/profile/mappen")
            list = (d["mappen"] as? [[String: Any]] ?? []).prefix(50).compactMap { MpMappe($0) }
            max = (d["max"] as? NSNumber)?.intValue ?? 50
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func create(_ name: String) async {
        let n = String(name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(60))
        guard !n.isEmpty, let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("POST", "api/profile/mappen", body: ["name": n])
            error = nil
            await load()
        } catch { self.error = error.localizedDescription }
    }

    /// only the assignment goes, never a document
    func delete(_ id: String) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            _ = try await api.object("DELETE", "api/profile/mappen/" + id)
            list.removeAll { $0.id == id }
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func detail(_ id: String) async -> MpDetail? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("GET", "api/profile/mappen/" + id)
            error = nil
            return MpDetail(d)
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    func setLevel(_ id: String, _ e: MpEintrag, _ stufe: String) async -> Bool {
        guard MpEintrag.stufen.contains(stufe), let api = SparkAPI.current else { return false }
        do {
            _ = try await api.object("PUT", "api/profile/mappen/" + id + "/eintrag", body: ["art": e.art, "ref": e.ref, "stufe": stufe])
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    /// takes an entry out of the Mappe; the document stays
    func remove(_ id: String, _ e: MpEintrag) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            _ = try await api.object("DELETE", "api/profile/mappen/" + id + "/eintrag", body: ["art": e.art, "ref": e.ref])
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }
}

/// Meine Sachen → Mappen: the own Mappen, a new one, delete one (with a question; the documents stay). Putting
/// documents in, notes and renaming stay in the panel (its way below).
struct MappenView: View {
    @StateObject private var m = MappenModel()
    @State private var neu = ""
    @State private var asking = false
    @State private var gone: MpMappe?

    var body: some View {
        List {
            if !m.loaded { LadeZeilen(rows: 3) }
            if m.loaded && m.list.isEmpty {
                Text("Noch keine Mappe. Eine Mappe bündelt Dokumente, Seiten des Wissensbuchs und Notizen zu einem Vorhaben; der Assistent antwortet dann nur daraus.")
                    .foregroundStyle(.secondary)
            }
            ForEach(m.list) { x in
                NavigationLink { MappeDetailView(mappe: x, model: m) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: x.name.isEmpty ? "?" : x.name)
                        Text(verbatim: [x.ziel, String(localized: "Einträge") + ": " + String(x.n)].filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                .swipeActions {
                    Button(role: .destructive) { gone = x } label: { Label("Löschen", systemImage: "trash") }
                }
            }
            Section {
                Text(SparkAPI.way(String(localized: "Dokumente hineinlegen, Notizen und Umbenennen gehen im Panel unter Mappen.")))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Mappen")
        .toolbar {
            Button { asking = true } label: { Label("Neue Mappe", systemImage: "plus") }.disabled(m.list.count >= m.max)
        }
        .alert("Neue Mappe", isPresented: $asking) {
            TextField("Name", text: $neu)
            Button("Anlegen") { let n = neu; neu = ""; Task { await m.create(n) } }
            Button("Abbrechen", role: .cancel) { neu = "" }
        }
        .confirmationDialog("Mappe löschen? Die Dokumente bleiben.", isPresented: Binding(get: { gone != nil }, set: { if !$0 { gone = nil } }),
                            titleVisibility: .visible) {
            Button("Mappe löschen", role: .destructive) { if let g = gone { Task { _ = await m.delete(g.id) } }; gone = nil }
        }
        .refreshable { await m.load() }
        .task { await m.load() }
    }
}

/// One Mappe: its entries with the level as a segmented control, the count „≈ … von … Token“ and „Mappe löschen“.
struct MappeDetailView: View {
    let mappe: MpMappe
    @ObservedObject var model: MappenModel
    @Environment(\.dismiss) private var dismiss
    @State private var d: MpDetail?
    @State private var loaded = false
    @State private var busy = false
    @State private var askDelete = false

    var body: some View {
        List {
            if let d {
                Section {
                    if !d.ziel.isEmpty { Text(verbatim: d.ziel).foregroundStyle(.secondary) }
                    ProgressView(value: Double(min(d.token, max(d.budget, 1))), total: Double(max(d.budget, 1)))
                    Text(String(localized: "≈ \(d.token) von \(d.budget) Token gehen mit jeder Frage an das Modell"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("Einträge") {
                    if d.eintraege.isEmpty {
                        Text("Noch leer. Leg im Panel Dokumente, Seiten oder eine Notiz hinein.").foregroundStyle(.secondary)
                    }
                    ForEach(d.eintraege) { e in row(e) }
                }
                Section {
                    Button("Mappe löschen", role: .destructive) { askDelete = true }
                }
            } else if !loaded {
                LadeZeilen(rows: 3)
            }
            if let e = model.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(Text(verbatim: mappe.name))
        .refreshable { await load() }
        .task { await load() }
        .confirmationDialog("Mappe löschen? Die Dokumente bleiben.", isPresented: $askDelete, titleVisibility: .visible) {
            Button("Mappe löschen", role: .destructive) {
                Task { if await model.delete(mappe.id) { dismiss() } }
            }
        }
    }

    @ViewBuilder private func row(_ e: MpEintrag) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: e.art == "seite" ? "book" : e.notiz ? "note.text" : "doc.text").foregroundStyle(.secondary)
                Text(verbatim: e.titel.isEmpty ? "?" : e.titel).lineLimit(2)
            }
            Picker("Stufe", selection: Binding(get: { e.stufe }, set: { s in Task { await change(e, s) } })) {
                ForEach(MpEintrag.stufen, id: \.self) { s in Text(verbatim: MpEintrag.stufeName(s)).tag(s) }
            }
            .pickerStyle(.segmented)
            .disabled(busy || e.grau)
            Text(verbatim: e.gehtText + " · " + String(localized: "kurz ≈ \(e.tokenKurz) · ganz ≈ \(e.tokenGanz) Token"))
                .font(.caption).foregroundStyle(.secondary)
        }
        .swipeActions {
            Button(role: .destructive) { Task { await take(e) } } label: { Label("Herausnehmen", systemImage: "minus.circle") }
        }
    }

    private func load() async {
        defer { loaded = true }
        if let got = await model.detail(mappe.id) { d = got }
    }

    private func change(_ e: MpEintrag, _ s: String) async {
        guard s != e.stufe else { return }
        busy = true
        defer { busy = false }
        if await model.setLevel(mappe.id, e, s) { await load() }   // the Spark counts again by its fixed rule
    }

    private func take(_ e: MpEintrag) async {
        busy = true
        defer { busy = false }
        if await model.remove(mappe.id, e) {
            await load()
            await model.load()
        }
    }
}
