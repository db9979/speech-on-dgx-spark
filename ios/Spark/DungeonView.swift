import SwiftUI

/// KI-Dungeon-Master (dungeon.py, Stufe 2 „5a“, Dominik 2026-10-23 „Alles umsetzten“): the own rounds, the kept heroes
/// and the campaigns with „Bisher geschah“, natively; a hero or a campaign is deleted here. „Spielen“ asks the Spark for
/// a code of the own seat (shown once, only its hash kept, a newer one replaces it) and opens the table of the panel in
/// the app (Safari view: microphone and reading aloud work there). New rounds and chapters start in the browser.
/// Opens with the admin's release of the Dungeon-Master (iphone.THINGS "dungeon"); every rule stays on the Spark.
struct DMRunde: Identifiable {
    let id: String
    let titel: String
    let laeuft: Bool
    let zug: Int
    let kapitel: Int
    let spieler: Int
    let held: String
    let host: Bool
}

struct DMHeld: Identifiable {
    let id: String
    let name: String
    let art: String
    let stufe: Int
    let leben: String
}

struct DMKampagne: Identifiable {
    let id: String
    let titel: String
    let welt: String
    let kapitel: Int
    let bisher: String
    let entwurf: Bool
    let schreibt: Bool
    let wer: String
}

@MainActor
final class DungeonModel: ObservableObject {
    @Published var runden: [DMRunde] = []
    @Published var helden: [DMHeld] = []
    @Published var kampagnen: [DMKampagne] = []
    @Published var loading = true
    @Published var error: String?
    @Published var play: PanelPlace?

    private func take(_ d: [String: Any]) {
        let n = { (x: Any?) in (x as? NSNumber)?.intValue ?? 0 }
        runden = (d["runden"] as? [[String: Any]] ?? []).prefix(40).map {
            DMRunde(id: $0["rid"] as? String ?? "", titel: $0["titel"] as? String ?? "", laeuft: $0["status"] as? String == "laeuft",
                    zug: n($0["zug"]), kapitel: n($0["kapitel"]), spieler: n($0["spieler"]), held: $0["held"] as? String ?? "",
                    host: $0["gastgeber"] as? Bool ?? false)
        }
        helden = (d["helden"] as? [[String: Any]] ?? []).prefix(20).map {
            DMHeld(id: $0["hid"] as? String ?? "", name: $0["name"] as? String ?? "",
                   art: [$0["volk"] as? String ?? "", $0["klasse"] as? String ?? ""].filter { !$0.isEmpty }.joined(separator: " "),
                   stufe: n($0["stufe"]), leben: "\(n($0["leben"]))/\(n($0["leben_max"]))")
        }
        kampagnen = (d["kampagnen"] as? [[String: Any]] ?? []).prefix(20).map {
            let wer = ($0["helden"] as? [String] ?? []) + ($0["gaeste"] as? [String] ?? [])
            return DMKampagne(id: $0["kid"] as? String ?? "", titel: $0["titel"] as? String ?? "", welt: $0["welt"] as? String ?? "",
                              kapitel: n($0["kapitel"]), bisher: $0["bisher"] as? String ?? "", entwurf: $0["entwurf"] as? Bool ?? false,
                              schreibt: $0["schreibt"] as? Bool ?? false, wer: wer.joined(separator: ", "))
        }
    }

    func load() async { await send("GET", "/api/profile/dungeon") }

    /// one change; the Spark answers with the whole page as it is now. true when it went through.
    @discardableResult
    func send(_ method: String, _ path: String, _ body: [String: Any]? = nil) async -> Bool {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); loading = false; return false }
        do {
            take(try await api.object(method, path, query: method == "GET" && Self.en ? ["lang": "en"] : [:], body: body))
            error = nil
            loading = false
            return true
        } catch {
            self.error = error.localizedDescription
            loading = false
            return false
        }
    }

    /// the table of a round with a code of the own seat, opened in the app
    func spielen(_ rid: String) async {
        guard let api = SparkAPI.current, let base = Store.baseURL else { return }
        do {
            let d = try await api.object("POST", "/api/profile/dungeon/\(rid)/sitzcode", body: [:])
            guard let code = d["code"] as? String, code.range(of: #"^[A-Za-z0-9_\-]{32}$"#, options: .regularExpression) != nil,
                  let url = URL(string: base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/#spiel=" + code)
            else { return }
            play = PanelPlace(url: url)
        } catch {
            self.error = error.localizedDescription
        }
    }

    static let en = Locale.current.language.languageCode?.identifier != "de"
}

struct DungeonView: View {
    @StateObject private var m = DungeonModel()

    var body: some View {
        List {
            if let e = m.error {
                Section { Text(SparkAPI.way(e)).foregroundStyle(.secondary) }
            }
            Section {
                if m.loading { LadeZeilen(rows: 2) }
                if !m.loading && m.runden.isEmpty { Text("Noch keine Runde.").foregroundStyle(.secondary) }
                ForEach(m.runden) { r in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: r.titel).font(.headline)
                            Text(zeile(r)).font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if r.laeuft {
                            Button("Spielen") { Task { await m.spielen(r.id) } }
                                .buttonStyle(.borderedProminent)
                        }
                    }
                }
            } header: { Text("Runden") } footer: {
                Text("Neue Runden und das nächste Kapitel legst du im Browser an. Spielen öffnet den Spieltisch hier in der App.")
            }
            Section("Meine Helden") {
                if !m.loading && m.helden.isEmpty { Text("Noch keine Helden.").foregroundStyle(.secondary) }
                ForEach(m.helden) { h in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: h.name).font(.headline)
                        Text("\(h.art) · Stufe \(h.stufe) · Leben \(h.leben)").font(.subheadline).foregroundStyle(.secondary)
                    }
                    .swipeActions {
                        Button("Löschen", role: .destructive) { Task { await m.send("DELETE", "/api/profile/dungeon/held/" + h.id) } }
                    }
                }
            }
            if !m.kampagnen.isEmpty {
                Section("Kampagnen") {
                    ForEach(m.kampagnen) { k in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(verbatim: k.titel).font(.headline)
                            Text("\(k.welt) · Kapitel \(k.kapitel)").font(.subheadline).foregroundStyle(.secondary)
                            if k.schreibt {
                                Text("Der Dungeon-Master schreibt die Zusammenfassung …").font(.footnote).foregroundStyle(.secondary)
                            } else if !k.bisher.isEmpty {
                                Text(verbatim: k.bisher).font(.footnote)
                                if k.entwurf { Text("Entwurf").font(.caption).foregroundStyle(.orange) }
                            }
                            if !k.wer.isEmpty { Text(verbatim: k.wer).font(.caption).foregroundStyle(.secondary) }
                        }
                        .swipeActions {
                            Button("Löschen", role: .destructive) { Task { await m.send("DELETE", "/api/profile/dungeon/kampagne/" + k.id) } }
                        }
                    }
                }
            }
        }
        .navigationTitle("Dungeon-Master")
        .task { await m.load() }
        .refreshable { await m.load() }
        .sheet(item: $m.play, onDismiss: { Task { await m.load() } }) { p in PanelPage(url: p.url).ignoresSafeArea() }
    }

    private func zeile(_ r: DMRunde) -> String {
        var a: [String] = []
        if r.kapitel > 0 { a.append(String(localized: "Kapitel \(r.kapitel)")) }
        a.append(String(localized: "Zug \(r.zug)"))
        a.append(String(localized: "\(r.spieler) Spieler"))
        if !r.held.isEmpty { a.append(r.held) }
        if !r.laeuft { a.append(String(localized: "beendet")) }
        return a.joined(separator: " · ")
    }
}
