import SwiftUI

/// Spark verwalten → Schwachstellen (schwachstellen.py, plan ios-nativ Paket 2, Dominik 2026-11-14): the same
/// /api/admin/schwach as Zustand → Schwachstellen in the panel. The findings by what to do (the groups' names come
/// from the Spark, `aktionen`), one finding with its ids, „Als Issue melden“, „Bewusst hinnehmen“ with a reason and
/// „Jetzt prüfen“. Only names, versions, ids, numbers and fixed words; the Spark checks every step again.
struct SchwachView: View {
    @State private var d: [String: Any] = [:]
    @State private var loaded = false
    @State private var error: String?
    @State private var busy = false

    private var funde: [[String: Any]] { d["funde"] as? [[String: Any]] ?? [] }

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
            if !loaded && d.isEmpty {
                LadeZeilen(rows: 3)
            } else if d["on"] as? Bool == false {
                Section { Text(SparkAPI.way(String(localized: "Schwachstellen sind aus. Einschalten unter Funktionen → Schwachstellen."))) }
            } else {
                Section {
                    Label { Text(verbatim: Self.satz(d)) } icon: {
                        Image(systemName: Self.lvl(d) == 2 ? "exclamationmark.octagon.fill" : Self.lvl(d) == 1 ? "exclamationmark.triangle.fill" : "checkmark.shield.fill")
                            .foregroundStyle(Self.lvl(d) == 2 ? Theme.bad : Self.lvl(d) == 1 ? Theme.warn : Theme.ok)
                    }
                    if let t = d["t"] as? Int, t > 0 {
                        LabeledContent(d["fehler"] as? Bool == true ? LocalizedStringKey("Zuletzt ohne Antwort, Stand") : LocalizedStringKey("Zuletzt geprüft")) {
                            Text(Date(timeIntervalSince1970: TimeInterval(t)), format: .dateTime.weekday().hour().minute())
                        }
                    }
                }
                ForEach(groups(), id: \.0) { name, list in
                    Section {
                        ForEach(list.indices, id: \.self) { i in
                            NavigationLink { SchwachFundView(key: list[i]["key"] as? String ?? "", outer: $d) } label: { Self.row(list[i], d) }
                        }
                    } header: { Text(verbatim: name) }
                }
                Section {
                    Button { Task { await check() } } label: {
                        if busy { ProgressView() } else { Text("Jetzt prüfen") }
                    }.disabled(busy)
                } footer: {
                    Text(SparkAPI.way(String(localized: "Fragt OSV nach allen Paketen auf Pi, tars, in den Abbildern und Apps. Ein Update spielt „Spark-Version“ in den Einstellungen der App ein.")))
                }
            }
        }
        .navigationTitle("Schwachstellen")
        .refreshable { await load() }
        .task { await load() }
    }

    /// the findings grouped like the panel: what to do (`aktion`), the knowingly accepted ones last
    private func groups() -> [(String, [[String: Any]])] {
        let names = d["aktionen"] as? [String: Any] ?? [:]
        var out: [(String, [[String: Any]])] = []
        for f in funde {
            let g = f["hin"] is [String: Any] ? String(localized: "Bewusst hingenommen")
                : FeaturesView.pick(names[f["aktion"] as? String ?? ""]) ?? (f["aktion"] as? String ?? "")
            if let i = out.firstIndex(where: { $0.0 == g }) { out[i].1.append(f) } else { out.append((g, [f])) }
        }
        return out
    }

    static func lvl(_ d: [String: Any]) -> Int {
        let z = d["zahl"] as? [String: Int] ?? [:]
        return (z["kritisch"] ?? 0) > 0 ? 2 : (z["hoch"] ?? 0) > 0 ? 1 : 0
    }

    static func satz(_ d: [String: Any]) -> String {
        let z = d["zahl"] as? [String: Int] ?? [:]
        let n = (d["funde"] as? [[String: Any]] ?? []).filter { !($0["hin"] is [String: Any]) }.count
        if (d["t"] as? Int ?? 0) == 0 { return String(localized: "Noch nicht geprüft.") }
        if n == 0 { return String(localized: "Keine bekannte Lücke.") }
        if let k = z["kritisch"], k > 0 { return String(localized: "\(k) kritisch, \(n) Funde.") }
        if let h = z["hoch"], h > 0 { return String(localized: "\(h) hoch, \(n) Funde.") }
        return String(localized: "\(n) Funde.")
    }

    static func stufe(_ s: String) -> (LocalizedStringKey, Color) {
        switch s {
        case "kritisch": return ("Kritisch", Theme.bad)
        case "hoch": return ("Hoch", Theme.warn)
        case "mittel": return ("Mittel", .secondary)
        case "niedrig": return ("Niedrig", .secondary)
        default: return ("Unbekannt", .secondary)
        }
    }

    static func name(_ f: [String: Any]) -> String {
        "\(f["n"] as? String ?? "") \(f["v"] as? String ?? "")".trimmingCharacters(in: .whitespaces)
    }

    /// where: the place's name from the Spark (`ort_name`, schwachstellen.ORT_NAME) and the venv, lock file or app part
    static func wo(_ f: [String: Any], _ d: [String: Any]) -> String {
        let o = f["ort"] as? String ?? ""
        let name = FeaturesView.pick((d["ort_name"] as? [String: Any])?[o]) ?? o
        return [name, o == "os" ? "" : f["wo"] as? String ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    @ViewBuilder static func row(_ f: [String: Any], _ d: [String: Any]) -> some View {
        let s = stufe(f["stufe"] as? String ?? "")
        HStack {
            VStack(alignment: .leading) {
                Text(verbatim: name(f))
                Text(verbatim: wo(f, d))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(s.0).font(.caption.weight(.semibold)).foregroundStyle(s.1)
        }
    }

    private func load() async {
        defer { loaded = true }
        do { d = try await AdminSession.shared.object("GET", "api/admin/schwach"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func check() async {
        busy = true
        defer { busy = false }
        do { d = try await AdminSession.shared.object("POST", "api/admin/schwach/pruefen", body: [:], timeout: 180); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

/// One finding: where, fixed in, the ids (osv.dev), the issue, accepted until; „Als Issue melden“ and „Bewusst
/// hinnehmen“ (a reason of 3 to 200 characters, `hin_tage` days, this version only) or „Nicht mehr hinnehmen“.
struct SchwachFundView: View {
    let key: String
    @Binding var outer: [String: Any]
    @State private var asking = false
    @State private var grund = ""
    @State private var msg: String?
    @State private var busy = false

    private var tage: Int { outer["hin_tage"] as? Int ?? 30 }
    private var f: [String: Any]? { (outer["funde"] as? [[String: Any]] ?? []).first { $0["key"] as? String == key } }

    var body: some View {
        List {
            if let f {
                let s = SchwachView.stufe(f["stufe"] as? String ?? "")
                Section {
                    LabeledContent("Schweregrad") {
                        Text(s.0).foregroundStyle(s.1)
                        if let c = f["score"] as? Double { Text(verbatim: " · CVSS \(c)") }
                    }
                    LabeledContent("Wo") { Text(verbatim: SchwachView.wo(f, outer)) }
                    LabeledContent("Behoben in") {
                        if let b = f["behoben"] as? String, !b.isEmpty { Text(verbatim: b) } else { Text("noch keine Version") }
                    }
                    if let i = f["issue"] as? [String: Any], let nr = i["nr"] as? Int {
                        if let u = (i["url"] as? String).flatMap(URL.init(string:)), u.host == "github.com" {
                            Link(destination: u) { LabeledContent("Issue") { Text(verbatim: "#\(nr)") } }
                        } else {
                            LabeledContent("Issue") { Text(verbatim: "#\(nr)") }
                        }
                    }
                    if let h = f["hin"] as? [String: Any] {
                        LabeledContent("Hingenommen bis") {
                            Text(Date(timeIntervalSince1970: TimeInterval(h["bis"] as? Int ?? 0)), format: .dateTime.day().month())
                        }
                        Text(verbatim: h["grund"] as? String ?? "").foregroundStyle(.secondary)
                    }
                } header: { Text(verbatim: SchwachView.name(f)) }
                let ids = (f["ids"] as? [String] ?? []).filter { $0.range(of: #"^[A-Za-z0-9._:-]{3,60}$"#, options: .regularExpression) != nil }
                if !ids.isEmpty {
                    Section("Kennungen") {
                        ForEach(ids, id: \.self) { i in
                            if let u = URL(string: "https://osv.dev/vulnerability/" + i) { Link(i, destination: u) }
                        }
                    }
                }
                Section {
                    if !ids.isEmpty && !(f["issue"] is [String: Any]) {
                        if outer["melden"] as? Bool == true {
                            Button("Als Issue melden") { Task { await post("api/admin/schwach/melden", ["key": key], done: String(localized: "Gemeldet.")) } }
                        } else {
                            Text(SparkAPI.way(String(localized: "Als Issue melden braucht Probleme melden mit GitHub-Token: Funktionen → Zugang → Probleme melden")))
                                .font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    if f["hin"] is [String: Any] {
                        Button("Nicht mehr hinnehmen") { Task { await post("api/admin/schwach/hinnehmen", ["key": key, "weg": true], done: nil) } }
                    } else {
                        Button("Bewusst hinnehmen …") { grund = ""; asking = true }
                    }
                    if busy { ProgressView() }
                    if let m = msg { Text(SparkAPI.way(m)).foregroundStyle(.secondary) }
                } footer: {
                    Text(SparkAPI.way(String(localized: "Was zu tun ist und wie weit die Stelle erreichbar ist, steht bei Zustand → Schwachstellen.")))
                }
            } else {
                Text("Diesen Fund gibt es nicht mehr.").foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Fund")
        .alert("Bewusst hinnehmen", isPresented: $asking) {
            TextField("Grund", text: $grund)
            Button("Hinnehmen") { Task { await post("api/admin/schwach/hinnehmen", ["key": key, "grund": String(grund.prefix(200))], done: nil) } }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Warum? Gilt \(tage) Tage und nur für diese Version.")
        }
    }

    private func post(_ path: String, _ body: [String: Any], done: String?) async {
        busy = true
        defer { busy = false }
        do {
            let d = try await AdminSession.shared.object("POST", path, body: body)
            if d["funde"] != nil { outer = d } else if let n = try? await AdminSession.shared.object("GET", "api/admin/schwach") { outer = n }
            msg = done
        } catch { msg = error.localizedDescription }
    }
}
