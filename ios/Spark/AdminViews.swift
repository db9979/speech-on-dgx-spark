import LocalAuthentication
import SwiftUI
import UIKit

/// "Spark verwalten": the admin's part of the panel in the app. Since V01.0.541 (plan plaene/admin-ohne-zweite-stufe.md)
/// a profile with an admin role is admin in its own app by the app's key, without a second login: the Spark checks
/// the role and the profile's second step with every request. The panel password (emergency access) stays in the
/// browser. Face ID guards the area in the app.
@MainActor
final class AdminSession: ObservableObject {
    static let shared = AdminSession()

    @Published private(set) var signedIn = false
    @Published var version = ""
    /// the profile's role on the Spark: "admin", "manager" or "" (none, or resting without the second step)
    @Published private(set) var role = ""
    private let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.httpCookieAcceptPolicy = .never
        c.timeoutIntervalForRequest = 60
        return URLSession(configuration: c)
    }()

    /// Asks the Spark what this app's profile may (whoami with the app's key).
    func refresh() async {
        let who: [String: Any]
        do { who = try await object("GET", "api/whoami") } catch {
            // the Spark restarting (an update) is no sign-out: the admin pages stay as they are (plaene/ruhige-seiten.md)
            if NetWatch.offline(error) { return }
            signedIn = false; role = ""; return
        }
        version = who["version"] as? String ?? ""
        let by = who["admin_by"] as? String ?? ""
        role = ["admin", "manager"].contains(by) ? by : ""
        signedIn = !role.isEmpty
    }

    func call(_ method: String, _ path: String, query: [String: String] = [:], body: [String: Any]? = nil,
              code: String? = nil, timeout: TimeInterval = 60) async throws -> Data {
        guard let base = Store.baseURL else { throw SparkError(message: String(localized: "Nicht gekoppelt.")) }
        var c = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { c.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) } }
        var r = URLRequest(url: c.url!)
        r.httpMethod = method
        r.timeoutInterval = timeout
        // the app's own key: the Spark checks the profile's role and its second step with every request
        if let key = Store.key { r.setValue(key, forHTTPHeaderField: "X-Speech-Device") }
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await SparkAPI.confirmed(r, code: code, session: session)
        if (response as? HTTPURLResponse)?.statusCode == 401 && path != "api/whoami" {
            signedIn = false
            throw SparkError(message: String(localized: "Dein Profil ist gerade kein Admin (Rolle oder zweiter Anmeldeschritt fehlt)."))
        }
        try SparkAPI.check(data, response)
        return data
    }

    func object(_ method: String, _ path: String, query: [String: String] = [:], body: [String: Any]? = nil,
                code: String? = nil, timeout: TimeInterval = 60) async throws -> [String: Any] {
        SparkAPI.object(try await call(method, path, query: query, body: body, code: code, timeout: timeout))
    }

    static func unlock(_ reason: String) async -> Bool {
        let ctx = LAContext()
        var err: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) else { return false }
        return (try? await ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason)) ?? false
    }
}

struct AdminView: View {
    @ObservedObject private var s = AdminSession.shared
    @State private var unlocked = false

    var body: some View {
        Form {
            if !unlocked {
                Section {
                    Button("Mit Face ID entsperren") { Task { unlocked = await AdminSession.unlock(String(localized: "Spark verwalten")) } }
                } footer: { Text("Dein Profil ist Admin; Face ID schützt diesen Bereich auf dem iPhone.") }
            } else if !s.signedIn {
                Section {
                    Text("Dein Profil ist gerade kein Admin.")
                } footer: {
                    Text(SparkAPI.way(String(localized: "Admin-Rechte gibt es nur mit dem zweiten Anmeldeschritt deines Profils (Ich → Sicherheit). Das Panel-Passwort (Notzugang) geht nur im Browser.")))
                }
            } else {
                Section {
                    NavigationLink("Überblick") { StatusView() }
                    NavigationLink("Logs") { LogsView() }
                    if s.role != "manager" { NavigationLink("Prüfen") { ChecksView() } }
                    if s.role != "manager" { NavigationLink("Werkstatt") { WerkstattView() } }
                    if s.role != "manager" { NavigationLink("Verbrauch") { UsageView() } }
                    if s.role != "manager" { NavigationLink("Modelle") { ModelsView() } }
                    if s.role != "manager" { NavigationLink("Praxistest") { PraxisView() } }
                    if s.role != "manager" { NavigationLink("Wartungspause") { WartungView() } }
                } header: { Text("Zustand") }
                Section {
                    // only the admin switches functions on and off; a Verwalter lifts blocks (Dominik 2026-10-14)
                    if s.role != "manager" { NavigationLink("Funktionen") { FeaturesView() } }
                    // Fernzugang → Systeme (fernzugang.py): the cards, disconnect and remove here; the shell in the panel
                    if s.role != "manager" { NavigationLink("Fernzugang") { FernzugangView() } }
                    NavigationLink("Personen und Geräte") { AdminProfilesView() }
                    if s.role != "manager" { NavigationLink("Sicherungen") { BackupsView() } }
                } header: { Text("Ändern") } footer: {
                    Text("Schutz-Änderungen (Rollen, Sicherungen, zweiter Schritt) fragen nach Code oder Face ID. Sprachmodell, Engines und Ports bleiben im Browser.")
                }
            }
        }
        .navigationTitle("Spark verwalten")
        .task {
            if !unlocked { unlocked = await AdminSession.unlock(String(localized: "Spark verwalten")) }
            await s.refresh()
        }
    }
}

// ---------------------------------------------------------------- Zustand → Überblick

/// A timed poll's error, shown only from the second miss in a row (the Spark's restart during an update is one short
/// miss), at the end of the list: the page keeps its last data and nothing shifts by itself (plaene/ruhige-seiten.md)
struct PollMiss {
    private(set) var text: String?
    private var misses = 0
    mutating func ok() { misses = 0; text = nil }
    mutating func fail(_ e: Error) { misses += 1; if misses >= 2 { text = e.localizedDescription } }
}

/// Rows of a list that grows or changes while it is open keep their identity by what they say, not by their place
/// (a new line on top would otherwise redraw every row): the text, and a counter for lines that say the same.
func stableRows(_ rows: [[String: Any]], _ key: ([String: Any]) -> String) -> [(id: String, row: [String: Any])] {
    var seen: [String: Int] = [:]
    return rows.map { (r: [String: Any]) -> (id: String, row: [String: Any]) in
        let k = key(r), n = seen[k, default: 0]
        seen[k] = n + 1
        return (id: n == 0 ? k : k + "#\(n)", row: r)
    }
}

struct StatusView: View {
    @State private var d: [String: Any] = [:]
    @State private var miss = PollMiss()
    @AppStorage("alertsOpen") private var alertsOpen = false

    private func alertRows(_ rows: [[String: Any]]) -> some View {
        ForEach(stableRows(rows) { ($0["text"] as? String ?? "") }, id: \.id) { item in
            let a = item.row
            Label {
                Text(verbatim: a["text"] as? String ?? "").lineLimit(2)
            } icon: {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(a["level"] as? String == "bad" ? .red : .orange)
            }
        }
    }

    var body: some View {
        List {
            let alerts = d["alerts"] as? [[String: Any]] ?? []
            // like the panel's notes on top (admin.js showAlerts): "bad" always open, from two others on they fold into
            // one line with the count, folded by default and remembered on this device
            let bad = alerts.filter { $0["level"] as? String == "bad" }, rest = alerts.filter { $0["level"] as? String != "bad" }
            Section("Braucht dich") {
                if alerts.isEmpty { Label("Alles in Ordnung", systemImage: "checkmark.circle").foregroundStyle(.green) }
                alertRows(bad)
                if rest.count > 1 {
                    DisclosureGroup(isExpanded: $alertsOpen) { alertRows(rest) } label: {
                        Label("\(rest.count) Hinweise", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                    }
                } else { alertRows(rest) }
            }
            let sys = d["system"] as? [String: Any] ?? [:], gpu = d["gpu"] as? [String: Any] ?? [:]
            // people with a request in the last 10 minutes (aktiv.py, the same number as on the case's display)
            let ak = (d["glance"] as? [String: Any])?["aktiv"] as? [String: Any] ?? [:]
            Section("Spark") {
                LabeledContent("Aktiv (10 min)") { Text(verbatim: Self.num(ak["gesamt"])) }
                LabeledContent("Profile / Gäste") { Text(verbatim: Self.num(ak["profile"]) + " / " + Self.num(ak["gaeste"])) }
                LabeledContent("Speicher frei") { Text(verbatim: Self.num(sys["mem_avail_gib"]) + " / " + Self.num(sys["mem_total_gib"]) + " GiB") }
                LabeledContent("CPU") { Text(verbatim: Self.num(sys["cpu"]) + " %") }
                LabeledContent("GPU") { Text(verbatim: Self.num(gpu["util"]) + " % · " + Self.num(gpu["temp"]) + " °C · " + Self.num(gpu["power"]) + " W") }
            }
            // Zustand → Überblick → Rechner (rechnerblick.py): with the models on another computer both computers side by
            // side like the panel's Spiegel-Karten (Dominik 2026-10-20): one row per value, the model computer left and
            // the panel computer right, the same rows in the same order, „–“ where a computer lacks a value, „Wer rechnet
            // gerade“ with always the same lines; numbers and fixed words only, the colour follows the panel's "stufe"
            let rech = d["rechner"] as? [String: Any] ?? [:]
            if rech["an"] as? Bool == true {
                let liste = rech["liste"] as? [[String: Any]] ?? []
                let m = liste.first { $0["id"] as? String == "modell" } ?? [:]
                let p = liste.first { $0["id"] as? String == "panel" } ?? [:]
                Section("Rechner") {
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(0..<2, id: \.self) { i in
                            let c = i == 0 ? m : p
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: Self.rechnerName(c)).font(.subheadline.weight(.semibold))
                                Text(Self.stufe(c)).font(.caption).foregroundStyle(Self.stufeFarbe(c))
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    ForEach(Self.vergleich(m, p), id: \.0) { _, name, a, b in
                        VStack(alignment: .leading, spacing: 2) {
                            if !name.isEmpty { Text(verbatim: name).font(.caption).foregroundStyle(.secondary) }
                            HStack(alignment: .top, spacing: 12) {
                                Text(verbatim: a).frame(maxWidth: .infinity, alignment: .leading)
                                Text(verbatim: b).frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .font(.callout.monospacedDigit())
                        }
                    }
                }
            }
            // Zustand → Überblick → Rundlauf (rundlauf.py): the last real round trip, each step in ms, the step that
            // hakt with its fixed word; numbers only
            let rd = d["rundlauf"] as? [String: Any] ?? [:]
            if rd["an"] as? Bool == true {
                let last = rd["letzt"] as? [String: Any] ?? [:]
                let ms = last["ms"] as? [String: Any] ?? [:]
                let bad = last["ok"] as? Bool == false ? last["step"] as? String ?? "" : ""
                Section("Rundlauf") {
                    LabeledContent("Zustand") {
                        Text(rd["stoerung"] is [String: Any] ? String(localized: "Störung") : last.isEmpty ? String(localized: "noch kein Lauf")
                             : bad.isEmpty ? String(localized: "kommt durch") : String(localized: "ein Fehler"))
                            .foregroundStyle(rd["stoerung"] is [String: Any] ? .red : bad.isEmpty ? .green : .orange)
                    }
                    ForEach([("tts", String(localized: "Sprechen")), ("asr", String(localized: "Hören")), ("llm", String(localized: "Sprachmodell"))], id: \.0) { k, name in
                        LabeledContent(name) {
                            Text(verbatim: bad == k ? String(localized: "Fehler") : Self.ms(ms[k])).foregroundStyle(bad == k ? .red : .primary)
                        }
                    }
                    LabeledContent("Ganzer Weg") { Text(verbatim: bad.isEmpty ? Self.ms(ms["ganz"]) : "–") }
                }
            }
            // Zustand → Überblick → Fernzugang (fernzugang.py): paired servers, online, open sessions; numbers only
            let fz = d["fernzugang"] as? [String: Any] ?? [:]
            if fz["on"] as? Bool == true {
                Section("Fernzugang") {
                    LabeledContent("Gekoppelt") { Text(verbatim: Self.num(fz["gekoppelt"] ?? 0)) }
                    LabeledContent("Online") { Text(verbatim: Self.num(fz["online"] ?? 0)) }
                    LabeledContent("Offene Sitzungen") {
                        Text(verbatim: Self.num(fz["sitzungen"] ?? 0)).foregroundStyle((fz["sitzungen"] as? Int ?? 0) > 0 ? .red : .primary)
                    }
                    if (fz["dateien"] as? Int ?? 0) > 0 { LabeledContent("Davon Dateien") { Text(verbatim: Self.num(fz["dateien"] ?? 0)) } }
                    if (fz["uebertragungen"] as? Int ?? 0) > 0 { LabeledContent("Übertragungen") { Text(verbatim: Self.num(fz["uebertragungen"] ?? 0)) } }
                    if (fz["abbau"] as? Int ?? 0) > 0 { LabeledContent("Warten auf Abbau") { Text(verbatim: Self.num(fz["abbau"] ?? 0)) } }
                    if (fz["hostkey"] as? Int ?? 0) > 0 {
                        LabeledContent("Host-Schlüssel falsch") { Text(verbatim: Self.num(fz["hostkey"] ?? 0)).foregroundStyle(.red) }
                    }
                    // per open session: kind, system, admin (names only with the panel's live_names), Zuhause or Internet, minutes
                    ForEach(Array((fz["offen"] as? [[String: Any]] ?? []).enumerated()), id: \.offset) { _, o in
                        LabeledContent {
                            Text(verbatim: "\(o["admin"] as? String ?? "Admin") · \(o["herkunft"] as? String ?? "") · \(Self.num(o["min"] ?? 0)) min").foregroundStyle(.red)
                        } label: {
                            Text(verbatim: "\(o["art"] as? String ?? "Shell") · \(o["system"] as? String ?? "")")
                        }
                    }
                }
            }
            // the "Heute" tiles of Zustand → Überblick (admin.glance): counts and times only; orange by the panel's rules
            let g = d["glance"] as? [String: Any] ?? [:]
            Section("Heute (24 Std.)") {
                // answers per hour of the last 24 hours, oldest first (admin.glance "hours"), as small bars
                if let hrs = g["hours"] as? [NSNumber], hrs.count == 24, hrs.contains(where: { $0.intValue > 0 }) {
                    let mx = max(1, hrs.map { $0.intValue }.max() ?? 1)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Antworten pro Stunde").font(.caption).foregroundStyle(.secondary)
                        HStack(alignment: .bottom, spacing: 2) {
                            ForEach(0..<24, id: \.self) { i in
                                let n = hrs[i].intValue
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(n > 0 ? Color.accentColor : Color.secondary.opacity(0.25))
                                    .frame(maxWidth: .infinity)
                                    .frame(height: n > 0 ? max(4, 48 * CGFloat(n) / CGFloat(mx)) : 2)
                            }
                        }
                        .frame(height: 48, alignment: .bottom)
                    }
                    .accessibilityElement(children: .combine)
                }
                LabeledContent { Text(verbatim: Self.num(g["answers"] ?? 0)) } label: { Label("Antworten", systemImage: "bubble.left") }
                if g["first_sound"] is NSNumber {
                    LabeledContent {
                        Text(verbatim: Self.num(g["first_sound"]) + " s").foregroundStyle(g["slower"] as? Bool == true ? .orange : .primary)
                    } label: { Label("Erster Ton", systemImage: "timer") }
                }
                if let sp = g["speakers"] as? [String: Any] {
                    let on = (sp["online"] as? NSNumber)?.intValue ?? 0, known = (sp["known"] as? NSNumber)?.intValue ?? 0
                    LabeledContent {
                        Text(verbatim: "\(on) / \(known)").foregroundStyle(on < known ? .orange : .green)
                    } label: { Label("Lautsprecher online", systemImage: "hifispeaker") }
                }
                if let held = ((g["background"] as? [String: Any])?["held"] as? NSNumber)?.intValue, held > 0 {
                    LabeledContent { Text(verbatim: "\(held)×") } label: { Label("Hintergrund wartete", systemImage: "waveform.path.ecg") }
                }
            }
            Section("Speech-Dienste") {
                ForEach(Self.services(d), id: \.0) { name, state in
                    LabeledContent(name) { Text(verbatim: state).foregroundStyle(Self.color(state)) }
                }
            }
            if let e = miss.text { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Überblick")
        .refreshable { await load() }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/status"); miss.ok() }
        catch { miss.fail(error) }
    }

    /// a step of the Rundlauf: ms below a second, seconds above
    static func ms(_ v: Any?) -> String {
        guard let n = (v as? NSNumber)?.intValue else { return "–" }
        return n >= 1000 ? String(format: "%.1f s", Double(n) / 1000) : "\(n) ms"
    }

    static func num(_ v: Any?) -> String {
        guard let n = (v as? NSNumber)?.doubleValue else { return "–" }
        return n == n.rounded() ? String(Int(n)) : String(format: "%.1f", n)
    }

    /// the rows of Zustand → Überblick → Rechner for both computers side by side, in the order of the panel's cards
    /// (admin.js zRCard): (key, name, model computer, panel computer); „–“ where a computer lacks the value
    static func vergleich(_ m: [String: Any], _ p: [String: Any]) -> [(String, String, String, String)] {
        var out: [(String, String, String, String)] = []
        func add(_ key: String, _ name: String, _ f: ([String: Any]) -> String) { out.append((key, name, f(m), f(p))) }
        add("cpu", "CPU") { num($0["cpu"]) + " %" }
        add("ram", String(localized: "Speicher frei")) { num($0["ram_frei"]) + " / " + num($0["ram_total"]) + " GiB" }
        add("gpu", "GPU") { c in
            guard c["id"] as? String == "modell" else { return "–" }
            let g = c["gpu"] as? [String: Any] ?? [:]
            return num(g["util"]) + " % · " + num(g["power"]) + " W"
        }
        add("temp", String(localized: "Temperatur")) { c in
            let g = c["gpu"] as? [String: Any] ?? [:]
            return num(c["temp"] is NSNumber ? c["temp"] : g["temp"]) + " °C"
        }
        add("platte", String(localized: "Platte frei")) { num($0["platte_frei"]) + " GB · " + num($0["platte_pct"]) + " %" }
        add("netz", String(localized: "Netz")) { "↓ " + num($0["netz_rx_mbs"]) + " ↑ " + num($0["netz_tx_mbs"]) + " MB/s" }
        add("eigen", "") { c in
            if c["id"] as? String == "modell" { return String(localized: "Sprachmodell") + ": " + (c["llm"] as? String ?? "–") }
            let hg = c["haenger"] as? [String: Any] ?? [:]
            return String(localized: "Panel hing") + ": \((hg["n"] as? NSNumber)?.intValue ?? 0)×"
        }
        let wm = wer(m), wp = wer(p)
        for i in 0..<max(wm.count, wp.count) {
            out.append(("wer\(i)", i == 0 ? String(localized: "Wer rechnet gerade") : "", i < wm.count ? wm[i] : "", i < wp.count ? wp[i] : ""))
        }
        add("dienste", String(localized: "Dienste")) { dienste($0) }
        return out
    }

    /// „Wer rechnet gerade“ of a computer (rechnerblick.wer): always the same lines, a resting service at 0 %, the
    /// panel's parts in the line under it, the rest, then the empty places; the panel sends the names in German and English
    static func wer(_ c: [String: Any]) -> [String] {
        let de = Locale.current.language.languageCode?.identifier == "de"
        let nm = { (x: [String: Any]) in (de ? x["name"] : x["en"]) as? String ?? x["name"] as? String ?? "" }
        let zeile = { (x: [String: Any]) in nm(x) + " " + num(x["pct"]) + " %" }
        let w = c["wer"] as? [String: Any] ?? [:]
        let z = w["zeilen"] as? [Any] ?? []
        guard w["gemessen"] as? Bool == true else {
            return [String(localized: "wird gemessen …")] + Array(repeating: "", count: z.count)
        }
        let da = z.compactMap { $0 as? [String: Any] }
        let panel = c["id"] as? String == "panel"
        let teile = (w["darin"] as? [[String: Any]] ?? []).map(zeile)
        let darin = "   " + String(localized: "darin") + ": " + (teile.isEmpty ? "–" : teile.joined(separator: " · "))
        var out: [String] = []
        for x in da {
            out.append(zeile(x))
            if panel && x["id"] as? String == "panel" { out.append(darin) }
        }
        if panel && !da.contains(where: { $0["id"] as? String == "panel" }) { out.append(darin) }
        out.append((w["rest"] as? [String: Any]).map(zeile) ?? "")
        return out + Array(repeating: "", count: max(0, z.count - da.count))
    }

    /// a computer of Zustand → Überblick → Rechner: its host name and its role
    static func rechnerName(_ c: [String: Any]) -> String {
        let rolle = c["id"] as? String == "modell" ? String(localized: "Modell-Rechner") : String(localized: "Panel-Rechner")
        let name = c["name"] as? String ?? ""
        return name.isEmpty ? rolle : name + " · " + rolle
    }

    static func stufe(_ c: [String: Any]) -> LocalizedStringKey {
        if c["id"] as? String == "modell" && c["ok"] as? Bool == false { return "antwortet nicht" }
        switch c["stufe"] as? String {
        case "bad": return "Fehler"
        case "warn": return "Hinweis"
        default: return "alles gut"
        }
    }

    static func stufeFarbe(_ c: [String: Any]) -> Color {
        ["ok": .green, "warn": .orange, "bad": .red][c["stufe"] as? String ?? ""] ?? .primary
    }

    /// "9 / 9 bereit": the computer's services that run or rest ready for a job ("bereit", rechnerblick.ABRUF)
    static func dienste(_ c: [String: Any]) -> String {
        let all = c["dienste"] as? [[String: Any]] ?? []
        let on = all.filter { ["active", "bereit"].contains($0["state"] as? String ?? "") }.count
        return "\(on) / \(all.count) " + String(localized: "bereit")
    }

    static func color(_ state: String) -> Color {
        ["active": .green, "bereit": .green, "activating": .orange, "failed": .red, "inactive": .secondary][state] ?? .primary
    }

    /// (name, state) of the speech services, their engines and the language model units
    static func services(_ d: [String: Any]) -> [(String, String)] {
        var out: [(String, String)] = []
        for (name, v) in (d["services"] as? [String: Any] ?? [:]).sorted(by: { $0.key < $1.key }) {
            guard let s = v as? [String: Any] else { continue }
            out.append((name.uppercased(), s["state"] as? String ?? "?"))
            for e in s["engines"] as? [[String: Any]] ?? [] {
                out.append(("  " + (e["name"] as? String ?? ""), e["state"] as? String ?? "?"))
            }
        }
        for q in d["qwen38"] as? [[String: Any]] ?? [] {
            out.append((q["unit"] as? String ?? "", q["state"] as? String ?? "?"))
        }
        return out
    }
}

// ---------------------------------------------------------------- Zustand → Verbrauch (verbrauch.py, admin only)

/// Zustand → Modelle (stage E1): the model catalog, the models that run, the memory budget and the last measurement.
/// With Funktionen → Modelle wechseln: „Wechseln“, „Zurückholen“, own models and „Messen“ per model.
struct ModelsView: View {
    @State private var d: [String: Any] = [:]
    @State private var error: String?
    @State private var ask: [String: String]?      // stage E4: {art, id, name} to switch, or {art, zurueck} to bring back
    @State private var eArt = "llm"                // stage E5: an own model from Hugging Face, found by „Suchen“
    @State private var eRepo = ""
    @State private var vorschlag: [String: Any]?
    @State private var offen = ""                  // the kind whose models show as a choice („Wechseln“ on its row)
    @State private var mehr = false                // „Mehr“: measurements, Lange Gespräche, Zurückholen
    @State private var suche = ""
    @State private var treffer: [[String: Any]]?
    @State private var platz = ""                  // „Lange Gespräche“: the picked choice (modelle.PLATZ)

    var body: some View {
        let w = d["wechsel"] as? [String: Any] ?? [:]
        let an = w["an"] as? Bool == true, misst = w["misst"] as? Bool == true
        let laeuft = w["laeuft"] as? Bool == true || misst      // a switch and a measurement never run at once
        let alte = w["alte"] as? [String: Any] ?? [:]
        let eigene = an && w["eigene"] as? Bool == true
        let arten = (d["arten"] as? [[String: Any]] ?? []).filter { !($0["modelle"] as? [[String: Any]] ?? []).isEmpty }
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let st = w["start"] as? [String: Any] { startSection(st) }
            if misst {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Eine Messung läuft. Das Sprachmodell pausiert so lange; die Zahlen erscheinen hier, sobald sie fertig ist.").foregroundStyle(.secondary)
                    let stand = w["stand"] as? [String] ?? []
                    if stand.isEmpty { ProgressView() } else {     // the measurement's own lines: fixed words and numbers
                        Text(verbatim: stand.joined(separator: "\n")).font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                }
            } else if laeuft && w["start"] == nil {
                Text(SparkAPI.way(String(localized: "Ein Modellwechsel läuft. Fortschritt unter Zustand → Logs."))).foregroundStyle(.secondary)
            }
            if let p = w["probe"] as? [String: Any], !laeuft || misst { probeSection(p) }
            let b = d["budget"] as? [String: Any] ?? [:]
            Section {
                let ges = (b["gesamt"] as? NSNumber)?.doubleValue ?? 0
                let belegt = ["fest", "system", "reserve"].reduce(0.0) { $0 + ((b[$1] as? NSNumber)?.doubleValue ?? 0) }
                if ges > 0 {
                    Self.balken(b, ges: ges)
                    Text("Grau: System und Reserve · heller: bei Bedarf · Bilder oder Musik: ein Platz, nie beide").font(.caption).foregroundStyle(.secondary)
                }
                LabeledContent("Fest belegt") { Text(verbatim: Self.gib(belegt) + " / " + Self.gib(ges)) }
                LabeledContent("Frei für Modelle bei Bedarf") { Text(verbatim: Self.gib(b["frei"])) }
                ForEach(Array(arten.enumerated()), id: \.offset) { _, a in
                    let art = a["art"] as? String ?? ""
                    let rows = a["modelle"] as? [[String: Any]] ?? []
                    let m = rows.first { $0["aktiv"] as? Bool == true }
                    let wahl = an && !laeuft && (rows.contains { $0["aktiv"] as? Bool != true && ($0["waehlbar"] as? Bool == true || $0["messbar"] as? Bool == true) }
                                                 || (eigene && (art == "llm" || art == "sehen")))
                    HStack {
                        if let m { Circle().fill(Self.farbe(art).opacity(m["betrieb"] as? String == "resident" ? 1 : 0.4)).frame(width: 10, height: 10) }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: a["name"] as? String ?? "").font(.caption).foregroundStyle(.secondary)
                            Text(verbatim: m?["name"] as? String ?? "–")
                            if let m { Text(verbatim: Self.kurz(m)).font(.caption).foregroundStyle(.secondary) }
                        }
                        Spacer()
                        if wahl {
                            Button(LocalizedStringKey(offen == art ? "Schließen" : "Wechseln")) { offen = offen == art ? "" : art; treffer = nil; suche = "" }
                                .buttonStyle(.bordered).font(.caption)
                        }
                    }
                }
            } header: { Text("Läuft jetzt") } footer: {
                if !an {
                    Text(SparkAPI.way(String(localized: "Zum Wechseln und Messen Funktionen → Modelle wechseln einschalten. Messen geht auch auf dem Spark: sudo speech-spark modelle messen")))
                }
            }
            if an && !laeuft, let a = arten.first(where: { $0["art"] as? String == offen }) {
                wahlSection(a, eigene: eigene)
                if eigene && (offen == "llm" || offen == "sehen") { sucheSection() }
            }
            Section {
                Button(LocalizedStringKey(mehr ? "Weniger anzeigen" : "Mehr: Lange Gespräche, Messwerte, Messen, Zurückholen")) { mehr.toggle() }
            }
            if mehr && !laeuft, let p = w["platz"] as? [String: Any] {
                let wahl = p["wahl"] as? [[String: Any]] ?? []
                let jetzt = p["jetzt"] as? String ?? "standard"
                Section {
                    Picker("Lange Gespräche", selection: Binding(get: { platz.isEmpty ? jetzt : platz }, set: { platz = $0 })) {
                        ForEach(Array(wahl.enumerated()), id: \.offset) { _, x in
                            let nein = x["nein"] as? String ?? ""
                            Text(verbatim: (x["name"] as? String ?? "") + ((x["plus_gib"] as? NSNumber)?.doubleValue ?? 0 > 0
                                ? " (+" + Self.gib(x["plus_gib"]) + ")" : "") + (nein.isEmpty || nein == "schon" ? "" : " ✕"))
                                .tag(x["id"] as? String ?? "")
                        }
                    }.pickerStyle(.inline).labelsHidden()
                    let gewaehlt = platz.isEmpty ? jetzt : platz
                    let ok = (wahl.first { $0["id"] as? String == gewaehlt }?["nein"] as? String ?? "x").isEmpty
                    Button("Übernehmen") { ask = ["platz": gewaehlt] }.disabled(gewaehlt == jetzt || !ok)
                } header: { Text("Lange Gespräche") } footer: {
                    Text("Alle Gespräche teilen sich einen Gesprächsspeicher. Mehr Platz kostet Speicher, der Bildern, Musik und dem Sehen-Modell fehlt. Das Sprachmodell startet dafür neu.")
                }
            }
            if mehr {
                ForEach(Array(arten.enumerated()), id: \.offset) { _, a in
                    let rows = a["modelle"] as? [[String: Any]] ?? []
                    let art = a["art"] as? String ?? ""
                    Section {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, m in
                            LabeledContent {
                                Text(verbatim: ((m["gemessen"] as? Bool ?? false) ? "" : "~") + Self.gib(m["aktiv"] as? Bool == true ? (m["gib"] ?? m["need_gib"]) : m["need_gib"]))
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(verbatim: m["name"] as? String ?? "")
                                    if m["aktiv"] as? Bool == true { Text("läuft").font(.caption).foregroundStyle(.green) }
                                    if let t = Self.mess(m["messung"]) { Text(verbatim: t).font(.caption).foregroundStyle(.secondary) }
                                    if !laeuft && m["messbar"] as? Bool == true {
                                        Button("Messen") {
                                            ask = ["id": m["id"] as? String ?? "", "name": m["name"] as? String ?? "", "messen": "1"]
                                        }.font(.caption).buttonStyle(.borderless)
                                    }
                                }
                            }
                        }
                        if an, let alt = alte[art] as? [String: Any], (alt["tage_frei"] as? Int ?? 0) > 0, !laeuft {
                            Button("Vorheriges Modell zurückholen") { ask = ["art": art, "zurueck": "1"] }
                        }
                    } header: { Text(verbatim: a["name"] as? String ?? "") }
                }
            }
        }
        .navigationTitle("Modelle")
        .refreshable { await load() }
        .task { await load() }
        .task(id: misst || startet) {      // while a measurement runs or the language model starts: every few seconds
            while (misst || startet) && !Task.isCancelled {
                try? await Task.sleep(for: .seconds(8))
                await load()
                if (d["wechsel"] as? [String: Any])?["misst"] as? Bool != true && !startet { break }
            }
        }
        .confirmationDialog(LocalizedStringKey(ask?["probe"] != nil ? "Modell ausprobieren?" : ask?["verwerfen"] != nil
                                               ? "Frage verwerfen?" : ask?["zurueck"] != nil ? "Vorheriges Modell zurückholen?" : ask?["loeschen"] != nil
                                               ? "Eigenes Modell löschen?" : ask?["dazu"] != nil ? "Eigenes Modell hinzufügen?"
                                               : ask?["messen"] != nil ? "Modell messen?" : ask?["platz"] != nil
                                               ? "Lange Gespräche einstellen?" : "Modell wechseln?"),
                            isPresented: Binding(get: { ask != nil }, set: { if !$0 { ask = nil } }), titleVisibility: .visible) {
            Button("Ja") { if let a = ask { Task { await send(a) } } }
        } message: {
            if ask?["probe"] != nil {
                Text("Der Spark lädt es falls nötig und misst es; das Sprachmodell pausiert für etwa 10 bis 25 Minuten. Danach fragt die Seite, ob gewechselt wird.")
            } else if ask?["verwerfen"] != nil {
                Text("Gewechselt wird nichts.")
            } else if ask?["messen"] != nil {
                Text("Das Sprachmodell pausiert für etwa 10 bis 25 Minuten und startet danach wieder. Gewechselt wird nichts.")
            } else if ask?["platz"] != nil {
                Text("Das Sprachmodell startet dafür neu und antwortet ein paar Minuten nicht.")
            } else if ask?["loeschen"] != nil {
                Text("Das Modell kommt aus der Liste und von der Platte.")
            } else if ask?["dazu"] != nil, let v = vorschlag {
                Text(verbatim: String(format: String(localized: "Stand %@, Platte %@ GB, Speicher ~%@, Lizenz %@. Geladen wird erst beim Ausprobieren."),
                                      String((v["revision"] as? String ?? "").prefix(12)), "\((v["platte_gb"] as? NSNumber)?.intValue ?? 0)",
                                      Self.gib(v["need_gib"]), v["lizenz"] as? String ?? ""))
            } else {
                Text("Der Spark lädt und prüft das Modell; das alte bleibt 7 Tage zum Zurückholen.")
            }
        }
    }

    /// The language model switches or starts and has not ended yet (llmstart).
    private var startet: Bool {
        ((d["wechsel"] as? [String: Any])?["start"] as? [String: Any])?["ende"] as? Bool == false
    }

    /// Dominik 2026-10-18 „5a“: the same six steps as the panel's card; the texts come from the panel (llmstart.zeigen).
    /// When it is done, the heading says so and every admin gets a note.
    @ViewBuilder private func startSection(_ x: [String: Any]) -> some View {
        let zeilen = x["zeilen"] as? [[String: Any]] ?? []
        Section {
            ForEach(Array(zeilen.enumerated()), id: \.offset) { _, z in
                let zustand = z["zustand"] as? String ?? "offen"
                HStack {
                    Image(systemName: zustand == "ok" ? "checkmark.circle.fill" : zustand == "jetzt" ? "circle.dotted" : "circle")
                        .foregroundStyle(zustand == "ok" ? Color.green : zustand == "jetzt" ? Color.accentColor : Color.secondary)
                    Text(verbatim: z["name"] as? String ?? "")
                    Spacer()
                    Text(verbatim: z["zeit"] as? String ?? "").font(.caption).foregroundStyle(.secondary)
                }
            }
            if let r = x["rest"] as? String, !r.isEmpty { Text(verbatim: r).foregroundStyle(.secondary) }
        } header: { Text(verbatim: x["kopf"] as? String ?? "") } footer: {
            if x["ende"] as? Bool == false {
                Text("Solange antwortet das Sprachmodell nicht; der Chat sagt das mit der erwarteten Zeit.")
            }
        }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/admin/modelle", query: ["lang": UsageView.de ? "de" : "en"]); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func send(_ a: [String: String]) async {
        let lang = ["lang": UsageView.de ? "de" : "en"]
        do {
            if a["probe"] != nil {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/messen", query: lang, body: ["id": a["id"] ?? "", "probe": true])
            } else if a["verwerfen"] != nil {
                d = try await AdminSession.shared.object("DELETE", "api/admin/modelle/probe", query: lang)
            } else if a["messen"] != nil {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/messen", query: lang, body: ["id": a["id"] ?? ""])
            } else if let p = a["platz"] {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/platz", query: lang, body: ["platz": p])
                platz = ""
            } else if a["loeschen"] != nil {
                let id = (a["id"] ?? "").addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? ""
                d = try await AdminSession.shared.object("DELETE", "api/admin/modelle/eigen/" + id, query: lang)
            } else if a["dazu"] != nil, let v = vorschlag {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/eigen", query: lang,
                                                         body: ["art": eArt, "repo": eRepo.trimmingCharacters(in: .whitespaces),
                                                                "revision": v["revision"] as? String ?? ""])
                treffer = treffer?.filter { $0["repo"] as? String != eRepo }
                vorschlag = nil; eRepo = ""
            } else if a["zurueck"] != nil {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/zurueck", query: lang, body: ["art": a["art"] ?? ""])
            } else {
                d = try await AdminSession.shared.object("POST", "api/admin/modelle/wechseln", query: lang,
                                                         body: ["art": a["art"] ?? "", "id": a["id"] ?? ""])
            }
            error = nil
        } catch { self.error = error.localizedDescription }
        ask = nil
    }

    /// „Hinzufügen“ on a hit: the full check of the newest commit, then the question with what would be added.
    private func dazu(_ repo: String) async {
        vorschlag = nil
        do {
            let r = try await AdminSession.shared.object("POST", "api/admin/modelle/eigen/pruefen", body: ["art": offen, "repo": repo])
            vorschlag = r["vorschlag"] as? [String: Any]; eArt = offen; eRepo = repo; error = nil
            if vorschlag != nil { ask = ["dazu": "1", "name": repo] }
        } catch { self.error = error.localizedDescription }
    }

    private func suchen() async {
        let q = suche.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return }
        do {
            let r = try await AdminSession.shared.object("POST", "api/admin/modelle/eigen/suche", body: ["art": offen, "q": q])
            treffer = r["treffer"] as? [[String: Any]] ?? []; error = nil
        } catch { self.error = error.localizedDescription }
    }

    /// After „Ausprobieren“: still measuring, broke off, or the numbers with „Wechseln“.
    @ViewBuilder private func probeSection(_ p: [String: Any]) -> some View {
        let name = p["name"] as? String ?? ""
        Section {
            if p["fertig"] as? Bool != true {
                Text(verbatim: String(format: String(localized: "„%@“ wird ausprobiert: erst laden und messen, dann fragt die Seite hier."), name))
            } else if p["ok"] as? Bool != true {
                Text(verbatim: String(format: String(localized: "„%@“: die Messung ist abgebrochen. Das jetzige Modell bleibt."), name))
                Button("Verwerfen") { ask = ["verwerfen": "1"] }
            } else {
                let t = (p["tok_s"] as? NSNumber).map { String(format: "%.1f tok/s", $0.doubleValue) } ?? "–"
                let j = (p["jetzt_tok_s"] as? NSNumber).map { String(format: "%.1f tok/s", $0.doubleValue) } ?? "–"
                LabeledContent(LocalizedStringKey("Ausprobiert")) { Text(verbatim: t) }
                LabeledContent { Text(verbatim: j) } label: { Text(verbatim: p["jetzt_name"] as? String ?? "") }
                if p["waehlbar"] as? Bool == true {
                    Button("Wechseln") { ask = ["art": p["art"] as? String ?? "", "id": p["id"] as? String ?? "", "name": name] }
                }
                Button("Verwerfen") { ask = ["verwerfen": "1"] }
            }
        } header: { Text(verbatim: name) }
    }

    /// „Wechseln“ on a kind: its models with what can be done with each.
    @ViewBuilder private func wahlSection(_ a: [String: Any], eigene: Bool) -> some View {
        let art = a["art"] as? String ?? ""
        Section {
            ForEach(Array((a["modelle"] as? [[String: Any]] ?? []).enumerated()), id: \.offset) { _, m in
                let nein = m["nein"] as? String ?? ""
                let probe = (nein == "revision" || nein == "ungeprueft") && m["messbar"] as? Bool == true
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: m["name"] as? String ?? "")
                        Text(verbatim: Self.kurz(m)).font(.caption).foregroundStyle(.secondary)
                        if m["gewerblich"] as? Bool == false { Text("nur privat").font(.caption).foregroundStyle(.orange) }
                    }
                    Spacer()
                    if m["aktiv"] as? Bool == true {
                        Text("läuft").font(.caption).foregroundStyle(.green)
                    } else if m["waehlbar"] as? Bool == true {
                        Button("Wechseln") { ask = ["art": art, "id": m["id"] as? String ?? "", "name": m["name"] as? String ?? ""] }
                            .buttonStyle(.bordered).font(.caption)
                    } else if probe {
                        Button("Ausprobieren") { ask = ["id": m["id"] as? String ?? "", "name": m["name"] as? String ?? "", "probe": "1"] }
                            .buttonStyle(.bordered).font(.caption)
                    } else {
                        Text(LocalizedStringKey(Self.nein[nein] ?? "nicht wählbar")).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .swipeActions {
                    if eigene && m["eigen"] as? Bool == true && m["aktiv"] as? Bool != true {
                        Button("Löschen", role: .destructive) {
                            ask = ["id": m["id"] as? String ?? "", "name": m["name"] as? String ?? "", "loeschen": "1"]
                        }
                    }
                }
            }
        } header: { Text(verbatim: a["name"] as? String ?? "") } footer: {
            Text("„Ausprobieren“ lädt das Modell falls nötig und misst es; danach fragt die Seite mit den Zahlen, ob gewechselt wird. Das alte Modell bleibt 7 Tage zum Zurückholen.")
        }
    }

    /// „Bei Hugging Face suchen“: the hits with the quick rules; „Hinzufügen“ checks the commit again.
    @ViewBuilder private func sucheSection() -> some View {
        Section {
            HStack {
                TextField("Suchwort", text: $suche).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .onSubmit { Task { await suchen() } }
                Button("Suchen") { Task { await suchen() } }.disabled(suche.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if let l = treffer, l.isEmpty { Text("Nichts gefunden.").foregroundStyle(.secondary) }
            ForEach(Array((treffer ?? []).enumerated()), id: \.offset) { _, h in
                let nein = h["nein"] as? String ?? ""
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: h["repo"] as? String ?? "")
                        Text(verbatim: [(h["gb"] as? NSNumber).map { String(format: "%.1f GB", $0.doubleValue) } ?? "",
                                        h["lizenz"] as? String ?? "", "\((h["downloads"] as? NSNumber)?.intValue ?? 0) ⬇"]
                            .filter { !$0.isEmpty }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if nein.isEmpty {
                        Button("Hinzufügen") { Task { await dazu(h["repo"] as? String ?? "") } }.buttonStyle(.bordered).font(.caption)
                    } else {
                        Text(LocalizedStringKey(Self.nein[nein] ?? "geht nicht")).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        } header: { Text("Bei Hugging Face suchen") } footer: {
            Text("Nur offene Modelle mit safetensors, ohne eigenen Code, mit einer Bauart, die die Engine kennt, und die in den Speicher passen.")
        }
    }

    /// Why a model or a hit cannot be picked (the panel's fixed words).
    static let nein = ["revision": "noch nicht gemessen", "aus": "erst umziehen", "budget": "zu knapp", "engine": "nicht wählbar",
                       "ungeprueft": "erst messen", "schon": "schon in der Liste", "zugang": "privat oder mit Freigabe",
                       "code": "braucht eigenen Code", "format": "keine safetensors", "architektur": "Bauart unbekannt",
                       "docker": "Docker: vorerst nur messen"]

    /// One line: measured tempo, memory, on demand.
    /// The memory bar like the panel's: one colored piece per running model, system and reserve grey, on demand lighter.
    static func farbe(_ art: String) -> Color {
        let rgb: [String: (Double, Double, Double)] = ["llm": (0.36, 0.42, 0.94), "sehen": (0.66, 0.33, 0.97), "asr": (0.06, 0.73, 0.51),
                                                       "tts": (0.02, 0.71, 0.83), "bild": (0.93, 0.28, 0.6), "musik": (0.96, 0.62, 0.04),
                                                       "klein": (0.52, 0.8, 0.09)]
        guard let c = rgb[art] else { return .gray }
        return Color(red: c.0, green: c.1, blue: c.2)
    }

    static func balken(_ b: [String: Any], ges: Double) -> some View {
        let num = { (x: Any?) in (x as? NSNumber)?.doubleValue ?? 0 }
        let teile = b["teile"] as? [[String: Any]] ?? []
        let teil = { (x: [String: Any]) in (AnyShapeStyle(farbe(x["art"] as? String ?? "").opacity(x["betrieb"] as? String == "resident" ? 1 : 0.4)), num(x["gib"])) }
        // pictures and music share one place (never both loaded): one piece of the bigger one in both colors
        let einPlatz = b["ein_platz"] as? [String] ?? []
        let platz = teile.filter { $0["betrieb"] as? String != "resident" && einPlatz.contains($0["art"] as? String ?? "") }
        let geteilt = platz.count > 1
        let farben = platz.map { farbe($0["art"] as? String ?? "").opacity(0.4) }
        var seg = teile.filter { $0["betrieb"] as? String == "resident" }.map(teil)
            + [(AnyShapeStyle(Color.gray), num(b["system"])), (AnyShapeStyle(Color.gray.opacity(0.5)), num(b["reserve"]))]
            + teile.filter { $0["betrieb"] as? String != "resident" && !(geteilt && einPlatz.contains($0["art"] as? String ?? "")) }.map(teil)
        if geteilt { seg.append((AnyShapeStyle(LinearGradient(colors: farben, startPoint: .leading, endPoint: .trailing)), platz.map { num($0["gib"]) }.max() ?? 0)) }
        let skala = max(ges, seg.reduce(0) { $0 + $1.1 })
        return GeometryReader { g in
            HStack(spacing: 1) {
                ForEach(Array(seg.enumerated()), id: \.offset) { _, s in
                    Rectangle().fill(s.0).frame(width: max(0, g.size.width * s.1 / skala - 1))
                }
                Spacer(minLength: 0)
            }
        }
        .frame(height: 12).background(Color.secondary.opacity(0.15)).clipShape(RoundedRectangle(cornerRadius: 4))
    }

    static func kurz(_ m: [String: Any]) -> String {
        var out: [String] = []
        if let t = ((m["messung"] as? [String: Any])?["tok_s"] as? NSNumber)?.doubleValue { out.append(String(format: "%.1f tok/s", t)) }
        out.append(((m["gemessen"] as? Bool ?? true) ? "" : "~") + gib(m["aktiv"] as? Bool == true ? (m["gib"] ?? m["need_gib"]) : m["need_gib"]))
        if m["betrieb"] as? String == "bei_bedarf" { out.append(String(localized: "bei Bedarf")) }
        return out.joined(separator: " · ")
    }

    static func gib(_ v: Any?) -> String {
        guard let n = (v as? NSNumber)?.doubleValue else { return "–" }
        return String(format: "%.1f GiB", n)
    }

    /// The last measurement in numbers only (no words to translate): tempo, first word, 2 and 4 at once, the long
    /// question and the room for 64K conversations; nil when not measured, "–" when it broke off.
    static func mess(_ v: Any?) -> String? {
        guard let x = v as? [String: Any], !x.isEmpty else { return nil }
        if x["ok"] as? Bool == false { return "–" }
        let n = { (k: String) in (x[k] as? NSNumber)?.doubleValue }
        var out: [String] = []
        if let t = n("tok_s") { out.append(String(format: "%.1f tok/s", t)) }
        if let t = n("erste_s") { out.append(String(format: "%.2f s", t)) }
        for p in [2, 4] { if let t = n("par\(p)_tok_s") { out.append(String(format: "%d× %.1f tok/s", p, t)) } }
        if let t = n("lang_tokens"), let e = n("lang_erste_s") { out.append(String(format: "%.0fK %.1f s", t / 1000, e)) }
        if let t = n("platz_64k") { out.append(String(format: "64K ×%.0f", t)) }
        return out.isEmpty ? nil : out.joined(separator: " · ")
    }
}

/// Zustand → Praxistest (panel/praxistest.py): the points of the hands-on test still open, the newest first; per point
/// „Klappt“, „Problem“, „Später“. The steps are German, as the threads wrote them.
struct PraxisView: View {
    @State private var d: [String: Any] = [:]
    @State private var error: String?

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            let all = d["punkte"] as? [[String: Any]] ?? []
            let open = all.filter { ($0["alt"] as? Bool) != true && (($0["stand"] as? String ?? "").isEmpty || $0["stand"] as? String == "problem") }
            Section {
                ForEach(Array(open.enumerated()), id: \.offset) { _, p in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: p["titel"] as? String ?? "").font(.headline)
                        if p["stand"] as? String == "problem" { Text("Problem").font(.caption).foregroundStyle(.red) }
                        Text(SparkAPI.way(p["text"] as? String ?? "")).font(.subheadline)
                        Text(verbatim: (p["id"] as? String ?? "") + " · V01.0." + String(format: "%03d", (p["v"] as? Int) ?? 0)).font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Button("Klappt") { Task { await mark(p, "ok") } }.buttonStyle(.bordered).tint(.green)
                            if p["stand"] as? String != "problem" {
                                Button("Problem") { Task { await mark(p, "problem") } }.buttonStyle(.bordered).tint(.red)
                                Button("Später") { Task { await mark(p, "spaeter") } }.buttonStyle(.bordered)
                            }
                        }
                    }.padding(.vertical, 4)
                }
            } header: { Text("Offen") } footer: {
                Text(SparkAPI.way(String(localized: "Bei einem Problem: im Browser Zustand → Logs → Diagnose kopieren und mit der Nummer in den Thread geben.")))
            }
        }
        .navigationTitle("Praxistest")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/admin/praxistest"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func mark(_ p: [String: Any], _ stand: String) async {
        do { _ = try await AdminSession.shared.call("POST", "api/admin/praxistest/" + (p["id"] as? String ?? ""), body: ["stand": stand]); await load() }
        catch { self.error = error.localizedDescription }
    }
}

/// Zustand → Werkstatt (panel/werkstattseite.py, Dominik 2026-10-21 „1“): the workshop's results on the model computer,
/// the newest first, each with what it means and the next step. Looking into a problem and repairs need a description
/// and the code: they open the panel's page here in the app.
struct WerkstattView: View {
    @State private var d: [String: Any] = [:]
    @State private var error: String?
    @State private var open: PanelPlace?

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if d["an"] as? Bool == false {
                Text(SparkAPI.way(String(localized: "Die Werkstatt ist aus. Einschalten unter Funktionen → Werkstatt."))).foregroundStyle(.secondary)
            } else {
                Section {
                    Button("Alles testen") { Task { await start() } }.disabled(d["laeuft"] as? Bool == true)
                    if let url = SparkAPI.panelLink("go=werk") {
                        Button("Problem untersuchen oder reparieren") { open = PanelPlace(url: url) }
                    }
                    if probe["an"] as? Bool == true {
                        Button("Angriffe prüfen") { Task { await probeStart() } }.disabled(probe["laeuft"] as? Bool == true)
                    }
                } footer: {
                    Text("Alle Selbsttests laufen in einer abgeschotteten Kopie auf dem Modell-Rechner, ohne Sprachmodell. Dein Spark bleibt unberührt.")
                }
                if d["laeuft"] as? Bool == true {
                    Section { Label("Ein Auftrag läuft", systemImage: "hourglass") }
                }
                if probe["laeuft"] as? Bool == true {
                    Section { Label("Angriffsprobe läuft", systemImage: "hourglass") }
                }
                Section("Verlauf") {
                    let runs = probe["laeufe"] as? [[String: Any]] ?? []
                    ForEach(Array(runs.enumerated()), id: \.offset) { _, p in
                        NavigationLink(destination: AngriffsprobeView(p: p, tarnungen: probe["tarnungen"] as? [String: Any] ?? [:], changed: { await load() })) {
                            LabeledContent {
                                Text(verbatim: "\(Self.num(p["gehorcht"])) / \(Self.num(p["von"]))").foregroundStyle(Self.num(p["gehorcht"]) > 0 ? .orange : .secondary)
                            } label: {
                                VStack(alignment: .leading) {
                                    Text("Angriffsprobe")
                                    Text(verbatim: Self.when(p["zeit"])).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    let list = d["auftraege"] as? [[String: Any]] ?? []
                    ForEach(Array(list.enumerated()), id: \.offset) { _, a in
                        NavigationLink(destination: WerkstattEinsView(id: a["id"] as? String ?? "", arten: d["arten"] as? [String: Any] ?? [:], changed: { await load() })) {
                            LabeledContent {
                                Text(verbatim: Self.badge(a)).foregroundStyle(Self.color(a))
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(verbatim: Self.art(a["art"], d["arten"]))
                                    Text(verbatim: Self.when(a["zeit"])).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    if list.isEmpty && runs.isEmpty { Text("Noch keine Ergebnisse.").foregroundStyle(.secondary) }
                }
            }
        }
        .navigationTitle("Werkstatt")
        .refreshable { await load() }
        .task { await load() }
        .sheet(item: $open) { p in PanelPage(url: p.url).ignoresSafeArea() }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/admin/werkstatt"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func start() async {
        do { d = try await AdminSession.shared.object("POST", "api/admin/werkstatt/tests", body: [:]); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private var probe: [String: Any] { d["probe"] as? [String: Any] ?? [:] }

    private func probeStart() async {
        do { d = try await AdminSession.shared.object("POST", "api/admin/werkstatt/angriffsprobe", body: [:]); error = nil }
        catch { self.error = error.localizedDescription }
    }

    static func num(_ v: Any?) -> Int { (v as? NSNumber)?.intValue ?? 0 }
    static func when(_ v: Any?) -> String {
        let s = (v as? NSNumber)?.doubleValue ?? 0
        return s > 0 ? Date(timeIntervalSince1970: s).formatted(date: .abbreviated, time: .shortened) : ""
    }
    static func art(_ a: Any?, _ arten: Any?) -> String {
        let k = a as? String ?? ""
        let x = (arten as? [String: Any])?[k] as? [String: Any] ?? [:]
        return (UsageView.de ? x["de"] : x["en"]) as? String ?? k
    }
    static func failed(_ a: [String: Any]) -> Bool { a["grund"] as? String != "ok" && a["grund"] as? String != "leer" }
    static func badge(_ a: [String: Any]) -> String {
        let rot = num((a["tests"] as? [String: Any])?["rot"])
        let art = a["art"] as? String ?? ""
        if failed(a) { return String(localized: "Fehler") }
        if art == "tests" || art == "nachtest" { return rot > 0 ? "\(rot) " + String(localized: "rot") : String(localized: "alle grün") }
        if art == "messen" {
            let l = a["aufgaben"] as? [[String: Any]] ?? []
            return "\(l.filter { $0["ok"] as? Bool == true }.count) / \(l.count)"
        }
        return art == "reparatur" ? String(localized: "Vorschlag") : String(localized: "Antwort")
    }
    static func color(_ a: [String: Any]) -> Color {
        failed(a) || num((a["tests"] as? [String: Any])?["rot"]) > 0 ? .red : .secondary
    }
}

/// One result of the workshop: numbers, what red means, the red tests, the answer; „Nur die roten noch mal testen“
/// names only the result (the Spark takes the names from it) and „Löschen“.
struct WerkstattEinsView: View {
    let id: String
    let arten: [String: Any]
    let changed: () async -> Void
    @State private var a: [String: Any] = [:]
    @State private var error: String?
    @State private var asking = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            let ts = a["tests"] as? [String: Any] ?? [:]
            let rot = WerkstattView.num(ts["rot"])
            let namen = ts["rot_namen"] as? [String] ?? []
            let art = a["art"] as? String ?? ""
            Section {
                Text(verbatim: WerkstattView.art(a["art"], arten) + " · " + WerkstattView.when(a["zeit"])).font(.headline)
                if let v = a["version"] as? String, !v.isEmpty { LabeledContent("Version") { Text(verbatim: v) } }
                if art == "tests" || art == "nachtest" {
                    LabeledContent("grün") { Text(verbatim: "\(WerkstattView.num(ts["gruen"]))").foregroundStyle(.green) }
                    LabeledContent("rot") { Text(verbatim: "\(rot)").foregroundStyle(rot > 0 ? .red : .secondary) }
                    LabeledContent("wackelig") { Text(verbatim: "\(WerkstattView.num(ts["wackelig"]))") }
                    if WerkstattView.num(ts["nicht_gelaufen"]) > 0 {
                        LabeledContent("nicht gelaufen") { Text(verbatim: "\(WerkstattView.num(ts["nicht_gelaufen"]))").foregroundStyle(.secondary) }
                    }
                }
            } footer: {
                if WerkstattView.num(ts["nicht_gelaufen"]) > 0 {
                    Text("Nicht gelaufen: Diese Tests brauchen, was die Kopie absichtlich nicht hat (Browser, Dateien außerhalb von app/). Sie zählen nicht als grün; auf GitHub laufen sie bei jeder Version.")
                }
                if rot > 0 && art == "tests" {
                    Text("Rot heißt: der Test hat in der Kopie nicht bestanden. Ein Update gibt es nur für Versionen, die auf GitHub grün waren; meist fehlt der Kopie etwas (Internet, Daten, Browser). Dein Spark läuft davon unberührt.")
                }
            }
            if !namen.isEmpty {
                Section("Rote Tests") {
                    ForEach(namen, id: \.self) { Text(verbatim: $0).font(.caption.monospaced()) }
                }
            }
            if let text = a["text"] as? String, !text.isEmpty {
                Section("Antwort") { Text(verbatim: text).font(.callout) }
            }
            Section {
                if rot > 0 && namen.contains(where: { $0 != "selftest" }) {
                    Button("Nur die roten noch mal testen") { Task { await again() } }
                }
                Button("Löschen", role: .destructive) { asking = true }
            }
        }
        .navigationTitle("Ergebnis")
        .task { await load() }
        .confirmationDialog("Dieses Ergebnis löschen?", isPresented: $asking) {
            Button("Löschen", role: .destructive) { Task { await delete() } }
        }
    }

    private func load() async {
        do { a = try await AdminSession.shared.object("GET", "api/admin/werkstatt/" + id); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func again() async {
        do { _ = try await AdminSession.shared.call("POST", "api/admin/werkstatt/tests", body: ["von": id]); await changed(); dismiss() }
        catch { self.error = error.localizedDescription }
    }

    private func delete() async {
        do { _ = try await AdminSession.shared.call("DELETE", "api/admin/werkstatt/" + id); await changed(); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

/// One run of the Angriffsprobe (panel/angriffsprobe.py): how often the language model would have followed a hidden
/// order, per disguise and per attacked tool; numbers only, and „Löschen“.
struct AngriffsprobeView: View {
    let p: [String: Any]
    let tarnungen: [String: Any]
    let changed: () async -> Void
    @State private var error: String?
    @State private var asking = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            Section {
                Text(verbatim: WerkstattView.when(p["zeit"])).font(.headline)
                if let m = p["modell"] as? String, !m.isEmpty { LabeledContent("Sprachmodell") { Text(verbatim: m) } }
                LabeledContent("gehorcht") { Text(verbatim: "\(WerkstattView.num(p["gehorcht"])) / \(WerkstattView.num(p["von"]))") }
                if WerkstattView.num(p["fehler"]) > 0 { LabeledContent("Fehler") { Text(verbatim: "\(WerkstattView.num(p["fehler"]))") } }
            } footer: {
                Text("Gezählt wird, wie oft das Sprachmodell einen versteckten Befehl ausgeführt hätte. Passiert ist nichts: das Panel sperrt diese Werkzeuge nach fremdem Text mit festen Regeln.")
            }
            Section("Nach Tarnung") { rows(p["verpackungen"]) { k in
                let x = tarnungen[k] as? [String: Any] ?? [:]
                return (UsageView.de ? x["de"] : x["en"]) as? String ?? k } }
            Section("Nach angegriffenem Werkzeug") { rows(p["ziele"]) { $0 } }
            Section { Button("Löschen", role: .destructive) { asking = true } }
        }
        .navigationTitle("Angriffsprobe")
        .confirmationDialog("Dieses Ergebnis löschen?", isPresented: $asking) {
            Button("Löschen", role: .destructive) { Task { await delete() } }
        }
    }

    private func rows(_ v: Any?, _ name: @escaping (String) -> String) -> some View {
        let m = v as? [String: Any] ?? [:]
        return ForEach(m.keys.sorted(), id: \.self) { k in
            let n = m[k] as? [Any] ?? []
            LabeledContent { Text(verbatim: "\(WerkstattView.num(n.first)) / \(WerkstattView.num(n.last))") } label: { Text(verbatim: name(k)) }
        }
    }

    private func delete() async {
        do { _ = try await AdminSession.shared.call("DELETE", "api/admin/werkstatt/angriffsprobe/" + (p["id"] as? String ?? "")); await changed(); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

struct UsageView: View {
    @State private var d: [String: Any] = [:]
    @State private var zeit = "30t"
    @State private var error: String?
    @State private var asking = false

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if d["on"] as? Bool == false {
                Text(SparkAPI.way(String(localized: "Der Verbrauchszähler ist aus. Einschalten unter Funktionen → Verbrauchszähler."))).foregroundStyle(.secondary)
            } else {
                let today = d["today"] as? [String: Any] ?? [:]
                let llm = today["llm"] as? [String: Any] ?? [:], asr = today["asr"] as? [String: Any] ?? [:], tts = today["tts"] as? [String: Any] ?? [:]
                Section("Heute") {
                    LabeledContent("Sprachmodell") { Text(verbatim: Self.n(Self.d(llm["read"]) + Self.d(llm["written"])) + " Tokens") }
                    LabeledContent("Aus dem Zwischenspeicher") { Text(verbatim: Self.pct(llm["cached"], llm["read"])) }
                    LabeledContent("Sprache gehört / gesprochen") { Text(verbatim: Self.sec(asr["amount"]) + " / " + Self.sec(tts["amount"])) }
                }
                Section {
                    Picker("Zeitraum", selection: $zeit) {
                        Text("30 Tage").tag("30t")
                        Text("12 Monate").tag("12m")
                    }.pickerStyle(.segmented)
                }
                Section("Nach Modell") {
                    ForEach(Array((d["models"] as? [[String: Any]] ?? []).enumerated()), id: \.offset) { _, m in
                        LabeledContent { Text(verbatim: Self.amount(m)) } label: { Text(verbatim: Self.word(m["name"])) }
                    }
                }
                Section("Nach Profil") {
                    ForEach(Array((d["profiles"] as? [[String: Any]] ?? []).enumerated()), id: \.offset) { _, p in
                        LabeledContent { Text(verbatim: Self.n(Self.d(p["tokens"])) + " Tokens") } label: { Text(verbatim: Self.who(p)) }
                    }
                }
                let quota = d["quota"] as? [String: Any] ?? [:]
                if quota["on"] as? Bool == true {
                    Section {
                        ForEach(Array((d["profiles"] as? [[String: Any]] ?? []).filter { $0["kind"] as? String == "profil" }.enumerated()), id: \.offset) { _, p in
                            NavigationLink {
                                QuotaEditView(profile: p, quota: quota) { await load() }
                            } label: {
                                LabeledContent { Text(verbatim: Self.state(p)) } label: { Text(verbatim: Self.who(p)) }
                            }
                        }
                    } header: { Text("Kontingent") } footer: { Text("Grenzen je Profil für Tag, Woche und Monat beim Sprachmodell.") }
                }
                Section {
                    Button("Zähler leeren", role: .destructive) { asking = true }
                } footer: { Text("Nur Zahlen, nie Fragen oder Antworten.") }
            }
        }
        .navigationTitle("Verbrauch")
        .refreshable { await load() }
        .task(id: zeit) { await load() }
        .confirmationDialog("Alle Zähler leeren?", isPresented: $asking) {
            Button("Zähler leeren", role: .destructive) { Task { await clear() } }
        }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/admin/verbrauch", query: ["zeit": zeit]); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func clear() async {
        do { _ = try await AdminSession.shared.call("POST", "api/admin/verbrauch/leeren", body: [:]); await load() }
        catch { self.error = error.localizedDescription }
    }

    static var de: Bool { Locale.current.language.languageCode?.identifier == "de" }
    static func d(_ v: Any?) -> Double { (v as? NSNumber)?.doubleValue ?? 0 }
    static func n(_ v: Double) -> String {
        if v >= 1e6 { return String(format: de ? "%.2f Mio" : "%.2f M", v / 1e6) }
        if v >= 1e4 { return String(format: de ? "%.1f Tsd" : "%.1f k", v / 1e3) }
        return String(Int(v))
    }
    static func sec(_ v: Any?) -> String {
        let s = d(v)
        if s >= 3600 { return String(format: "%.1f h", s / 3600) }
        return s >= 60 ? "\(Int(s / 60)) min" : "\(Int(s)) s"
    }
    static func pct(_ a: Any?, _ b: Any?) -> String { d(b) > 0 ? "\(Int((100 * d(a) / d(b)).rounded())) %" : "–" }
    static func word(_ v: Any?) -> String {
        let a = v as? [String] ?? []
        return a.count == 2 ? (de ? a[0] : a[1]) : ""
    }
    static func amount(_ m: [String: Any]) -> String {
        switch m["unit"] as? String {
        case "tok": return n(d(m["read"]) + d(m["written"])) + " Tokens"
        case "sek": return sec(m["amount"])
        default: return n(d(m["amount"])) + " " + word(m["unit_name"])
        }
    }
    /// The fullest limit of a profile: "1,2 Mio / 2 Mio · Tag", "Woche voll" or "keine Grenze".
    static func state(_ p: [String: Any]) -> String {
        let lim = p["limits"] as? [String: Any] ?? [:], used = p["used"] as? [String: Any] ?? [:]
        var top: (String, Double, Double)?
        for z in ["tag", "woche", "monat"] where d(lim[z]) > 0 {
            if top == nil || d(used[z]) / d(lim[z]) > top!.1 / top!.2 { top = (z, d(used[z]), d(lim[z])) }
        }
        guard let t = top else { return de ? "keine Grenze" : "no limit" }
        let name = ["tag": de ? "Tag" : "day", "woche": de ? "Woche" : "week", "monat": de ? "Monat" : "month"][t.0] ?? t.0
        return t.1 >= t.2 ? name + (de ? " voll" : " full") : n(t.1) + " / " + n(t.2) + " · " + name
    }
    static func who(_ p: [String: Any]) -> String {
        switch p["kind"] as? String {
        case "gast": return de ? "Gäste" : "Guests"
        case "spark": return de ? "Spark selbst" : "The Spark itself"
        case "geloescht": return de ? "Gelöschte Profile" : "Deleted profiles"
        default: return p["name"] as? String ?? ""
        }
    }
}

/// One profile's own limits (thousand tokens; empty: the default, 0: none) and „+500 heute“, like Zustand → Verbrauch.
struct QuotaEditView: View {
    let profile: [String: Any]
    let quota: [String: Any]
    let reload: () async -> Void
    @State private var values: [String: String] = [:]
    @State private var error: String?
    @State private var done = false
    private let zeiten = ["tag", "woche", "monat"]

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            Section {
                ForEach(zeiten, id: \.self) { z in
                    LabeledContent {
                        TextField(String(describing: (quota["k"] as? [String: Any])?[z] ?? ""), text: Binding(get: { values[z] ?? "" }, set: { values[z] = $0 }))
                            .keyboardType(.numberPad).multilineTextAlignment(.trailing)
                    } label: { Text(verbatim: label(z)) }
                }
                Button("Setzen") { Task { await save() } }
            } header: { Text("Tausend Tokens") } footer: { Text("Leer gilt die Vorgabe, 0 heißt keine Grenze.") }
            Section {
                LabeledContent("Stand") { Text(verbatim: UsageView.state(profile)) }
                Button("+500 heute") { Task { await more() } }
            } footer: { Text("500 Tausend Tokens mehr bis Mitternacht, für jede Grenze.") }
            if done { Text("Gespeichert.").foregroundStyle(.secondary) }
        }
        .navigationTitle(Text(verbatim: profile["name"] as? String ?? ""))
        .onAppear {
            let own = ((quota["own"] as? [String: Any])?[profile["id"] as? String ?? ""] as? [String: Any]) ?? [:]
            for z in zeiten { if let v = own[z] as? Int { values[z] = String(v) } }
        }
    }

    private func label(_ z: String) -> String {
        let a = (quota["zeiten"] as? [String: Any])?[z] as? [String] ?? [z, z]
        return a.count == 2 ? (UsageView.de ? a[0] : a[1]) : z
    }

    private func save() async {
        let own = ((quota["own"] as? [String: Any])?[profile["id"] as? String ?? ""] as? [String: Any]) ?? [:]
        do {
            for z in zeiten {
                let text = (values[z] ?? "").trimmingCharacters(in: .whitespaces)
                let old = (own[z] as? Int).map(String.init) ?? ""
                if text == old { continue }
                var body: [String: Any] = ["uid": profile["id"] as? String ?? "", "zeit": z]
                if let v = Int(text) { body["k"] = v } else { body["k"] = NSNull() }
                _ = try await AdminSession.shared.call("PUT", "api/admin/verbrauch/kontingent", body: body)
            }
            error = nil; done = true
            await reload()
        } catch { self.error = error.localizedDescription }
    }

    private func more() async {
        do {
            _ = try await AdminSession.shared.call("POST", "api/admin/verbrauch/nachschlag", body: ["uid": profile["id"] as? String ?? "", "k": 500])
            error = nil; done = true
            await reload()
        } catch { self.error = error.localizedDescription }
    }
}

// ---------------------------------------------------------------- Zustand → Wartungspause (wartung.py)

/// The same card as Zustand → Wartungspause in the panel: pick the parts and the longest time, start; while it holds
/// the time left, "+15 min" and "Weiter". Only admins (the Spark checks it); parts and minutes come from the Spark.
struct WartungView: View {
    @State private var d: [String: Any] = [:]
    @State private var pick: Set<String> = ["llm"]
    @State private var minutes = 30
    @State private var error: String?

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if d["on"] as? Bool == false {
                Section { Text(SparkAPI.way(String(localized: "Die Wartungspause ist aus. Einschalten unter Funktionen → Wartungspause."))) }
            } else if d["paused"] as? Bool == true {
                Section {
                    Label { Text(verbatim: names(d["parts"] as? [String] ?? [])) } icon: {
                        Image(systemName: "pause.circle.fill").foregroundStyle(d["overdue"] as? Bool == true ? .orange : .blue)
                    }
                    if d["overdue"] as? Bool == true {
                        Text("Zeit um, wartet auf Antwort")
                    } else {
                        LabeledContent("Noch") { Text(verbatim: "\(d["left"] as? Int ?? 0) min") }
                    }
                    LabeledContent("Mit dem Wartungssatz beantwortet") { Text(verbatim: "\(d["asked"] as? Int ?? 0)") }
                    LabeledContent("Hintergrundarbeit wartet") { Text(verbatim: "\(d["held"] as? Int ?? 0)") }
                } header: { Text("Pause läuft") }
                Section {
                    Button("+15 min") { Task { await post("api/admin/wartung", ["more": true]) } }
                    Button("Weiter") { Task { await post("api/admin/wartung/weiter", [:]) } }
                }
            } else {
                Section {
                    ForEach(parts(), id: \.0) { key, name in
                        Toggle(isOn: Binding(get: { pick.contains(key) }, set: { v in if v { pick.insert(key) } else { pick.remove(key) } })) {
                            Text(verbatim: name)
                        }
                    }
                } header: { Text("Was wird aktualisiert?") }
                Section {
                    Picker("Höchstens", selection: $minutes) {
                        ForEach((d["choices"] as? [String: Any])?["minutes"] as? [Int] ?? [15, 30, 60, 120], id: \.self) {
                            Text(verbatim: "\($0) min").tag($0)
                        }
                    }
                    Button("Pause starten") {
                        Task { await post("api/admin/wartung", ["parts": Array(pick), "minutes": minutes, "channel": "app"]) }
                    }.disabled(pick.isEmpty)
                } footer: { Text("Solange die Pause läuft, antwortet der Spark sofort mit einem festen Satz; Hintergrundarbeit wartet.") }
            }
        }
        .navigationTitle("Wartungspause")
        .refreshable { await load() }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    private func parts() -> [(String, String)] {
        ((d["choices"] as? [String: Any])?["parts"] as? [[String]] ?? []).compactMap { p in
            p.count == 3 ? (p[0], FeaturesView.pick([p[1], p[2]]) ?? p[0]) : nil
        }
    }

    private func names(_ keys: [String]) -> String {
        let all = Dictionary(parts(), uniquingKeysWith: { a, _ in a })
        return keys.map { all[$0] ?? $0 }.joined(separator: ", ")
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/admin/wartung"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func post(_ path: String, _ body: [String: Any]) async {
        do { d = try await AdminSession.shared.object("POST", path, body: body); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

// ---------------------------------------------------------------- Zustand → Logs (Diagnose)

struct LogsView: View {
    /// the filter keys of the panel's diagnosis tab (logfilter.FILTERS)
    static let areas: [(String, LocalizedStringKey)] = [
        ("errors", LocalizedStringKey("Nur Fehler")), ("chat", LocalizedStringKey("Gespräch")), ("search", LocalizedStringKey("Websuche")),
        ("weiche", LocalizedStringKey("Weiche")), ("ha", LocalizedStringKey("Home Assistant")), ("room", LocalizedStringKey("Raum")),
        ("esp32", LocalizedStringKey("Lautsprecher")), ("watch", LocalizedStringKey("Uhr")), ("telegram", LocalizedStringKey("Telegram")),
        ("mail", LocalizedStringKey("Mail")), ("vorrang", LocalizedStringKey("Vorrang")), ("update", LocalizedStringKey("Update")),
    ]
    @AppStorage("logAreas") private var picked = "errors"
    @AppStorage("logMinutes") private var minutes = 60
    @State private var rows: [[String: Any]] = []
    @State private var head = ""
    @State private var last: [String: Any]?
    @State private var error: String?
    @State private var copied = false

    var body: some View {
        List {
            Section {
                Picker("Zeitraum", selection: $minutes) {
                    Text("10 Minuten").tag(10)
                    Text("1 Stunde").tag(60)
                    Text("2 Stunden").tag(120)
                    Text("12 Stunden").tag(720)
                    Text("1 Tag").tag(1440)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        chip("", LocalizedStringKey("Alle"))
                        ForEach(Self.areas, id: \.0) { chip($0.0, $0.1) }
                    }
                }
                Button {
                    UIPasteboard.general.string = copyText()
                    copied = true
                } label: { Label(copied ? LocalizedStringKey("Kopiert") : LocalizedStringKey("Kopieren für Thread"), systemImage: "doc.on.doc") }
                ShareLink(item: copyText()) { Label("Teilen", systemImage: "square.and.arrow.up") }
            }
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let l = last {
                Section("Letzter Fehler") {
                    Text(verbatim: (l["t"] as? String ?? "") + " · " + (l["msg"] as? String ?? "")).font(.footnote)
                    if let hint = l["hint"] as? [String: Any], let de = hint[Locale.current.language.languageCode?.identifier == "de" ? "de" : "en"] as? String {
                        Text(verbatim: de).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                ForEach(stableRows(rows) { ($0["t"] as? String ?? "") + "|" + ($0["msg"] as? String ?? "") }.reversed(), id: \.id) { item in
                    let r = item.row
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: (r["t"] as? String ?? "") + (((r["area"] as? String) ?? "").isEmpty ? "" : " · " + (r["area"] as? String ?? "")))
                            .font(.caption2).foregroundStyle(.secondary)
                        // log lines are plain text, never links or commands
                        Text(verbatim: r["msg"] as? String ?? "").font(.caption.monospaced())
                            .foregroundStyle(r["level"] as? String == "err" ? .red : r["level"] as? String == "warn" ? .orange : .primary)
                    }
                }
            } header: { Text(verbatim: head) }
        }
        .navigationTitle("Logs")
        .refreshable { await load() }
        .task(id: "\(picked)|\(minutes)") { await load() }
    }

    private func chip(_ key: String, _ title: LocalizedStringKey) -> some View {
        let on = key.isEmpty ? picked.isEmpty : picked.split(separator: ",").contains(Substring(key))
        return Button {
            var set = picked.split(separator: ",").map(String.init)
            if key.isEmpty { set = [] } else if on { set.removeAll { $0 == key } } else { set.append(key) }
            picked = set.joined(separator: ",")
            copied = false
        } label: { Text(title).font(.caption) }
        .buttonStyle(.bordered)
        .tint(on ? .accentColor : .secondary)
    }

    private func load() async {
        do {
            let d = try await AdminSession.shared.object("GET", "api/logfilter",
                                                         query: ["format": "json", "f": picked, "minutes": String(minutes), "lines": "300"])
            rows = d["rows"] as? [[String: Any]] ?? []
            head = d["head"] as? String ?? ""
            last = d["last_error"] as? [String: Any]
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    /// the same text as "Kopieren für Thread" in the panel
    private func copyText() -> String {
        let lines = rows.map { $0["raw"] as? String ?? "" }.joined(separator: "\n")
        return String(localized: "Speech auf DGX Spark") + " " + AdminSession.shared.version + " · " + head + "\n```\n" + lines + "\n```"
    }
}

// ---------------------------------------------------------------- Zustand → Prüfen

struct ChecksView: View {
    @State private var live: [String: Any] = [:]
    @State private var quality: [String: Any] = [:]
    @State private var vorrang: [String: Any] = [:]
    @State private var error: String?
    @State private var miss = PollMiss()

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            Section {
                let steps = live["steps"] as? [[String: Any]] ?? []
                ForEach(Array(steps.enumerated()), id: \.offset) { _, s in
                    LabeledContent {
                        Text(verbatim: StatusView.num(s["seconds"]) + " s")
                    } label: {
                        Label((s["name"] as? String ?? "").uppercased(),
                              systemImage: s["ok"] as? Bool == true ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(s["ok"] as? Bool == true ? .green : .red)
                    }
                }
                Button("Jetzt prüfen") { Task { await run("api/livecheck", timeout: 200) } }
            } header: { Text("Funktionsprüfung") } footer: { Text("Sprachmodell, Sprachausgabe und Spracherkennung einmal durch.") }
            Section {
                if let p = quality["progress"] as? [String: Any] {
                    ProgressView(value: (p["done"] as? NSNumber)?.doubleValue ?? 0, total: max(1, (p["total"] as? NSNumber)?.doubleValue ?? 1))
                } else if let l = quality["last"] as? [String: Any] {
                    LabeledContent("Bestanden") { Text(verbatim: StatusView.num(l["passed"]) + " / " + StatusView.num(l["total"])) }
                }
                Button("Qualitätstest starten") { Task { await run("api/quality") } }.disabled(quality["running"] as? Bool == true)
            } header: { Text("Qualitätstest") }
            Section {
                if vorrang["running"] as? Bool == true { ProgressView() }
                if let r = vorrang["result"] as? [String: Any] {
                    if let t = (r["verdict"] as? [String: Any])?["title"] as? [String: Any] {
                        Text(verbatim: (Locale.current.language.languageCode?.identifier == "de" ? t["de"] : t["en"]) as? String ?? "")
                    }
                    if let e = r["error"] as? String { Text(SparkAPI.way(e)).foregroundStyle(.red) }
                }
                Button("Vorrang prüfen") { Task { await run("api/vorrang") } }.disabled(vorrang["running"] as? Bool == true)
            } header: { Text("Vorrang für Sprache") } footer: { Text("Dauert etwa eine Minute.") }
            if let e = miss.text { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Prüfen")
        .refreshable { await load() }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(4))
            }
        }
    }

    private func load() async {
        let s = AdminSession.shared
        do {
            live = try await s.object("GET", "api/livecheck")
            quality = try await s.object("GET", "api/quality")
            vorrang = try await s.object("GET", "api/vorrang")
            miss.ok()
        } catch { miss.fail(error) }
    }

    private func run(_ path: String, timeout: TimeInterval = 60) async {
        do { _ = try await AdminSession.shared.call("POST", path, timeout: timeout); await load() }
        catch { self.error = error.localizedDescription }
    }
}


// MARK: - Ändern (Funktionen, Personen und Geräte, Sicherungen)

/// Funktionen: the plain on/off switches (the Spark names them; the sensitive ones stay in
/// the browser, where they want the admin's code).
struct FeaturesView: View {
    @ObservedObject private var s = AdminSession.shared
    @State private var on: [String: Bool] = [:]
    @State private var names: [String: String] = [:]
    @State private var groups: [SwitchGroup] = []
    @State private var grund = Grund()
    @State private var error: String?

    /// the Grundausstattung (features.GRUNDAUSSTATTUNG): what is still off and the internet question, as the Spark sends it
    struct Grund {
        var basis: [String] = []
        var off: [String] = []
        var internet: [String] = []
        var ask = false
        var names: [String: String] = [:]
    }

    /// a group of switches as the Spark sends it (features.py: names and groups, no list of its own in the app)
    struct SwitchGroup: Identifiable {
        let id: String
        let name: String
        let keys: [String]
    }

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if !grund.off.isEmpty || grund.ask { grundSection }
            ForEach(groups) { g in
                let keys = g.keys.filter { on[$0] != nil }
                if !keys.isEmpty {
                    Section { ForEach(keys, id: \.self) { toggle($0) } } header: { Text(verbatim: g.name) }
                }
            }
            let rest = on.keys.filter { k in !groups.contains { $0.keys.contains(k) } }.sorted()
            if !rest.isEmpty {
                Section { ForEach(rest, id: \.self) { toggle($0) } } header: { Text(verbatim: "Spark") }
            }
        }
        .navigationTitle("Funktionen")
        .refreshable { await load() }
        .task { await load() }
    }

    private func toggle(_ key: String) -> some View {
        Toggle(isOn: Binding(get: { on[key] ?? false }, set: { v in on[key] = v; Task { await save(key, v) } })) {
            if grund.basis.contains("chat." + key) {
                VStack(alignment: .leading) {
                    Text(verbatim: names[key] ?? key)
                    Text("Empfohlen").font(.caption).foregroundStyle(.green)
                }
            } else {
                Text(verbatim: names[key] ?? key)
            }
        }
    }

    /// the card of the panel's Funktionen page: take the whole list, answer the internet question
    @ViewBuilder private var grundSection: some View {
        Section {
            if !grund.off.isEmpty {
                Text("Geht ohne Einrichtung, bleibt im Spark und braucht kein Zusatzmodell. Gäste bekommen davon nichts.")
                    .font(.footnote)
                Text(verbatim: grund.off.compactMap { grund.names[$0] }.joined(separator: ", ")).font(.footnote).foregroundStyle(.secondary)
                Button("Alle übernehmen") { Task { await take(["teil": "basis", "on": true]) } }
            }
            if grund.ask {
                Text("Darf der Spark ins Internet? Für Wetter, Wikipedia, die Websuche über dein SearXNG und den Dienst-Wächter. Mails und Dokumente gehen nie hinaus.")
                    .font(.footnote)
                Button("Ja") { Task { await take(["teil": "internet", "on": true]) } }
                Button("Nein, nur im Heimnetz") { Task { await take(["teil": "internet", "on": false]) } }
            }
        } header: {
            Text("Grundausstattung für ein gutes Gespräch")
        } footer: {
            Text(SparkAPI.way(String(localized: "Zurücknehmen im Browser unter Zustand → Logs → Admin-Protokoll.")))
        }
    }

    static func parseGrund(_ x: Any?) -> Grund {
        guard let d = x as? [String: Any] else { return Grund() }
        let b = d["basis"] as? [String: Any] ?? [:], i = d["internet"] as? [String: Any] ?? [:]
        let keys = ((b["keys"] as? [String]) ?? []).prefix(60).map { $0 }, ons = Set((b["on"] as? [String]) ?? [])
        return Grund(basis: keys, off: keys.filter { !ons.contains($0) }, internet: (i["keys"] as? [String]) ?? [],
                     ask: (i["frage"] as? String) == "offen",
                     names: ((d["names"] as? [String: Any]) ?? [:]).compactMapValues { pick($0) })
    }

    private func take(_ body: [String: Any]) async {
        do {
            let d = try await s.object("POST", "api/admin/grundausstattung", body: body)
            grund = Self.parseGrund(d)
            error = nil
            await load()
        } catch { self.error = error.localizedDescription }
    }

    static func pick(_ x: Any?) -> String? {
        guard let a = x as? [String], a.count == 2 else { return nil }
        return String(a[(Locale.preferredLanguages.first?.hasPrefix("en") ?? false) ? 1 : 0].prefix(80))
    }

    private func load() async {
        do {
            let d = try await s.object("GET", "api/admin/switches")
            on = ((d["switches"] as? [String: Any]) ?? [:]).compactMapValues { $0 as? Bool }
            names = ((d["names"] as? [String: Any]) ?? [:]).compactMapValues { Self.pick($0) }
            grund = Self.parseGrund(d["grund"])
            groups = ((d["groups"] as? [[String: Any]]) ?? []).prefix(20).compactMap { g in
                guard let k = g["key"] as? String, let n = Self.pick(g["name"]) else { return nil }
                return SwitchGroup(id: k, name: n, keys: (g["switches"] as? [String]) ?? [])
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func save(_ key: String, _ value: Bool) async {
        do { _ = try await s.call("PUT", "api/admin/switches", body: ["key": key, "on": value]); error = nil }
        catch { self.error = error.localizedDescription; on[key] = !value }
    }
}

struct AdminProfile: Identifiable, Hashable {
    let id: String
    let name: String
    let devices: Int
    let mfa: Bool
    let last: Date?
}

/// Personen und Geräte: the profiles, a new one, a profile's devices; a new PIN, the second step reset and
/// deleting need the admin's code.
struct AdminProfilesView: View {
    @ObservedObject private var s = AdminSession.shared
    @State private var users: [AdminProfile] = []
    @State private var name = ""
    @State private var pin = ""
    @State private var error: String?
    @State private var note: String?

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            Section {
                ForEach(users) { u in
                    NavigationLink { AdminProfileView(user: u) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: u.name)
                            HStack {
                                Text("\(u.devices) Geräte")
                                if u.mfa { Text("zweiter Schritt") }
                                if let last = u.last { Text(last, format: .dateTime.day().month().year()) }
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            } header: { Text("Profile") }
            Section {
                TextField("Name", text: $name)
                SecureField("PIN (mindestens 4 Zeichen)", text: $pin)
                Button("Profil anlegen") { Task { await add() } }.disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || pin.count < 4)
            } header: { Text("Neues Profil") } footer: {
                Text(SparkAPI.way(String(localized: "Ein neues iPhone koppelt das Profil danach selbst unter Ich → iPhone-App.")))
            }
        }
        .navigationTitle("Personen und Geräte")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            let d = try await s.object("GET", "api/admin/profiles")
            users = (d["users"] as? [[String: Any]] ?? []).prefix(500).compactMap { x in
                guard let id = x["id"] as? String, id.range(of: #"^u_[0-9a-f]{6,32}$"#, options: .regularExpression) != nil else { return nil }
                let last = (x["last"] as? NSNumber)?.doubleValue ?? 0
                return AdminProfile(id: id, name: String((x["name"] as? String ?? "").prefix(40)), devices: (x["devices"] as? NSNumber)?.intValue ?? 0,
                                    mfa: x["mfa"] as? Bool ?? false, last: last > 0 ? Date(timeIntervalSince1970: last) : nil)
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func add() async {
        do {
            _ = try await s.call("POST", "api/admin/profiles", body: ["name": name.trimmingCharacters(in: .whitespaces), "pin": pin])
            note = String(localized: "Profil angelegt.")
            name = ""
            pin = ""
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

struct AdminProfileView: View {
    let user: AdminProfile
    @ObservedObject private var s = AdminSession.shared
    @Environment(\.dismiss) private var dismiss
    @State private var devices: [(id: String, name: String, app: Bool)] = []
    @State private var mfa = false
    @State private var pin = ""
    @State private var ask: CodeRequest?
    @State private var confirmDelete = false
    @State private var error: String?
    @State private var note: String?
    @State private var role = ""
    @State private var sessions: [(id: String, agent: String, last: Date?)] = []
    /// the functions on on the Spark and whether this profile may use them (Gesperrte Funktionen): on for every profile at
    /// once, the admin only blocks one here; "via" marks a block through a function it builds on
    @State private var funcs: [(key: String, name: String, on: Bool, via: Bool)] = []

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if !role.isEmpty {
                LabeledContent("Admin-Rechte") { Text(role == "owner" ? String(localized: "Haupt-Admin") : role == "manager" ? String(localized: "Verwalter") : String(localized: "Mit-Admin")) }
            }
            Section {
                ForEach(funcs, id: \.key) { f in
                    Toggle(isOn: Binding(get: { f.on && !f.via }, set: { v in Task { await setFunc(f.key, v) } })) {
                        Text(verbatim: f.name)
                        if f.via { Text("Gesperrt über eine Funktion, auf der sie aufbaut") }
                    }
                    .disabled(f.via || (s.role == "manager" && f.on))   // a Verwalter only lifts a block
                }
                if funcs.isEmpty { Text("Keine Funktion auf dem Spark an.").foregroundStyle(.secondary) }
            } header: { Text("Funktionen: \(funcsOn) von \(funcs.count) freigegeben") } footer: {
                if s.role == "manager" {
                    Text("Als Verwalter hebst du hier nur Sperren auf. Funktionen schalten und Profile sperren kann nur der Admin.")
                } else {
                    Text("Was auf dem Spark an ist, gilt sofort für jedes Profil. Aus sperrt eine Funktion nur für dieses Profil; das Profil kann die Sperre nicht selbst aufheben.")
                }
            }
            Section {
                ForEach(sessions, id: \.id) { x in
                    LabeledContent { if let l = x.last { Text(l, format: .dateTime.day().month().hour().minute()) } } label: { Text(verbatim: x.agent) }
                        .swipeActions { Button("Abmelden", role: .destructive) { Task { await endSession(x.id) } } }
                }
                if sessions.isEmpty { Text("Kein Browser angemeldet.").foregroundStyle(.secondary) }
            } header: { Text("Angemeldete Browser") } footer: { Text("Wischen meldet einen Browser ab.") }
            Section {
                ForEach(devices, id: \.id) { d in
                    LabeledContent { Text(d.app ? String(localized: "iPhone-App") : String(localized: "Gerät")) } label: { Text(verbatim: d.name) }
                        .swipeActions { Button("Entfernen", role: .destructive) { Task { await removeDevice(d.id) } } }
                }
                if devices.isEmpty { Text("Keine Geräte.").foregroundStyle(.secondary) }
            } header: { Text("Geräte") } footer: { Text("Wischen entfernt ein Gerät, sein Schlüssel gilt sofort nicht mehr.") }
            Section {
                SecureField("Neue PIN", text: $pin)
                Button("PIN setzen") { ask = CodeRequest { c in await setPin(code: c) } }.disabled(pin.count < 4)
                if mfa {
                    Button("Zweiten Schritt zurücksetzen") { ask = CodeRequest { c in await resetMfa(code: c) } }
                }
                Button("Profil löschen", role: .destructive) { confirmDelete = true }
            } header: { Text("Anmeldung") } footer: {
                Text("Zurücksetzen nur, wenn das Profil Handy und Wiederherstellungscodes verloren hat. Löschen entfernt Gedächtnis, Gespräche und Geräte.")
            }
        }
        .navigationTitle(Text(verbatim: user.name))
        .task { await load() }
        .codeAlert($ask)
        .confirmationDialog("Profil endgültig löschen?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) { ask = CodeRequest { c in await delete(code: c) } }
        }
    }

    private var path: String { "api/admin/profiles/\(user.id)" }

    private func load() async {
        do {
            let d = try await s.object("GET", path)
            mfa = d["mfa"] as? Bool ?? false
            role = d["role"] as? String ?? ""
            devices = (d["devices"] as? [[String: Any]] ?? []).prefix(50).compactMap { x in
                guard let id = x["id"] as? String, SparkAPI.devId(id) else { return nil }
                return (id, String((x["name"] as? String ?? "").prefix(40)), x["app"] as? Bool ?? false)
            }
            sessions = (d["sessions"] as? [[String: Any]] ?? []).prefix(50).compactMap { x in
                guard let id = x["id"] as? String, id.range(of: #"^[0-9a-f]{16}$"#, options: .regularExpression) != nil else { return nil }
                let last = (x["last"] as? NSNumber)?.doubleValue ?? 0
                return (id, String((x["agent"] as? String ?? "Browser").prefix(60)), last > 0 ? Date(timeIntervalSince1970: last) : nil)
            }
            let m = try await s.object("GET", "api/admin/features")
            funcs = (m["features"] as? [[String: Any]] ?? []).prefix(200).compactMap { f in
                guard let key = f["key"] as? String, key.range(of: #"^[a-z0-9_]{1,40}$"#, options: .regularExpression) != nil,
                      f["spark"] as? Bool == true, let cells = f["cells"] as? [String: Any],
                      let name = FeaturesView.pick(f["name"]) else { return nil }
                let via = (f["inherited"] as? [String: Any])?[user.id] as? Bool ?? false
                return (key, name, cells[user.id] as? Bool ?? true, via)
            }
        } catch { self.error = error.localizedDescription }
    }

    private var funcsOn: Int { funcs.filter { $0.on && !$0.via }.count }

    private func setFunc(_ key: String, _ on: Bool) async {
        do { _ = try await s.call("PUT", "api/admin/features/\(key)/profiles/\(user.id)", body: ["on": on]); error = nil }
        catch { self.error = error.localizedDescription }
        await load()
    }

    private func endSession(_ id: String) async {
        do { _ = try await s.call("DELETE", path + "/sessions/\(id)"); error = nil }
        catch { self.error = error.localizedDescription }
        await load()
    }

    private func removeDevice(_ id: String) async {
        guard SparkAPI.devId(id) else { return }
        do { _ = try await s.call("DELETE", "api/admin/devices/\(id)"); await load() }
        catch { self.error = error.localizedDescription }
    }

    private func setPin(code: String) async {
        do {
            _ = try await s.call("PUT", path, body: ["pin": pin], code: code)
            pin = ""
            note = String(localized: "Neue PIN gesetzt.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func resetMfa(code: String) async {
        do {
            _ = try await s.call("DELETE", path + "/mfa", code: code)
            note = String(localized: "Der zweite Schritt ist für dieses Profil aus.")
            await load()
        } catch { self.error = error.localizedDescription }
    }

    private func delete(code: String) async {
        do { _ = try await s.call("DELETE", path, code: code); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

/// Update und Sicherung: the backups on the Spark, a new one now, deleting an old one. Restoring and
/// downloading stay in the browser.
struct BackupsView: View {
    @ObservedObject private var s = AdminSession.shared
    @State private var items: [(name: String, size: Int, created: Date)] = []
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        Form {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            Section {
                Button { Task { await create() } } label: { if busy { ProgressView() } else { Text("Jetzt sichern") } }.disabled(busy)
            } footer: { Text("Zurückspielen und Herunterladen gehen im Browser.") }
            Section {
                ForEach(items, id: \.name) { b in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(b.created, format: .dateTime.day().month().year().hour().minute())
                        Text(verbatim: ByteCountFormatter.string(fromByteCount: Int64(b.size), countStyle: .file)).font(.caption).foregroundStyle(.secondary)
                    }
                    .swipeActions { if s.role == "admin" { Button("Löschen", role: .destructive) { Task { await remove(b.name) } } } }
                }
            } header: { Text("Sicherungen") }
        }
        .navigationTitle("Sicherungen")
        .refreshable { await load() }
        .task { await load() }
    }

    private static func valid(_ n: String) -> Bool {
        n.range(of: #"^speech-spark-\d{8}-\d{6}(-[a-z\-]{1,20})?\.tar\.gz$"#, options: .regularExpression) != nil
    }

    private func parse(_ d: [String: Any]) {
        items = (d["backups"] as? [[String: Any]] ?? []).prefix(100).compactMap { x in
            guard let n = x["name"] as? String, Self.valid(n) else { return nil }
            return (n, (x["size"] as? NSNumber)?.intValue ?? 0, Date(timeIntervalSince1970: (x["created"] as? NSNumber)?.doubleValue ?? 0))
        }
    }

    private func load() async {
        do { parse(try await s.object("GET", "api/backups")); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func create() async {
        busy = true
        defer { busy = false }
        do { _ = try await s.call("POST", "api/backups", timeout: 600); await load() }
        catch { self.error = error.localizedDescription }
    }

    private func remove(_ name: String) async {
        guard Self.valid(name) else { return }
        do { parse(try await s.object("DELETE", "api/backups/\(name)")) }
        catch { self.error = error.localizedDescription }
    }
}

// ---------------------------------------------------------------- Fernzugang → Systeme (fernzugang.py, stage 2)

/// One remote server as the Spark lists it (GET /api/admin/fernzugang): numbers, times and fixed words only.
struct FernServer: Identifiable {
    let id: String
    let name: String
    let os: String
    let anker: String
    let online: Bool
    let onlineSeit: Date?
    let weg: Date?
    let zuletzt: Date?
    let stand: String
    let erlaubt: Bool
    let hostkeyFalsch: Bool
    let fp: String
    let sitzungen: Int
}

/// The cards of Fernzugang → Systeme in the app: status, online, „Trennen“, „Alle trennen“, „Darf sich verbinden“
/// and „Entfernen“ (the same levels as in the panel, stufen.py). The shell and pairing need a login in a browser:
/// they open the panel page inside the app (SFSafariViewController), never the app's own key.
struct FernzugangView: View {
    @State private var d: [String: Any] = [:]
    @State private var servers: [FernServer] = []
    @State private var error: String?
    @State private var note: String?
    @State private var loaded = false
    @State private var open: PanelPlace?
    @State private var askAll = false
    @State private var askRemove: FernServer?

    var body: some View {
        List {
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if !loaded { LadeZeilen(rows: 3) }
            if loaded && d["on"] as? Bool == false {
                Text(SparkAPI.way(String(localized: "Der Fernzugang ist aus. Einschalten unter Funktionen → Fernzugang zu Servern."))).foregroundStyle(.secondary)
            } else if loaded {
                if d["notaus"] as? Bool == true {
                    Text("Notaus: der Fernzugang ist gesperrt, bis der Notaus aufgehoben ist.").foregroundStyle(.red)
                }
                let c = d["counts"] as? [String: Any] ?? [:]
                Section {
                    LabeledContent("Systeme verbunden") { Text(verbatim: "\(Self.num(c["online"])) / \(Self.num(c["gekoppelt"]))") }
                    LabeledContent("Offene Sitzungen") {
                        Text(verbatim: "\(Self.num(c["sitzungen"])) / \(Self.num(d["max"]))").foregroundStyle(Self.num(c["sitzungen"]) > 0 ? .red : .primary)
                    }
                    LabeledContent("Leerlauf trennt") { Text(verbatim: "\(Self.num(d["leerlauf"])) min") }
                } footer: {
                    Text("Nur Zahlen und feste Wörter; aufgezeichnet wird nichts.")
                }
                ForEach(servers) { g in
                    Section {
                        LabeledContent {
                            Text(Self.word(g)).foregroundStyle(Self.color(g))
                        } label: {
                            Label { Text(verbatim: g.name) } icon: { Image(systemName: "circle.fill").foregroundStyle(Self.color(g)) }
                        }
                        if let s = g.onlineSeit, g.online {
                            LabeledContent("Online seit") { Text(s, format: .dateTime.day().month().hour().minute()) }
                        } else if let w = g.weg {
                            LabeledContent("Offline seit") { Text(w, format: .dateTime.day().month().hour().minute()) }
                        }
                        if let z = g.zuletzt { LabeledContent("Letzte Sitzung") { Text(z, format: .dateTime.day().month().hour().minute()) } }
                        if !g.os.isEmpty || !g.anker.isEmpty {
                            LabeledContent("Anker") { Text(verbatim: [g.anker, g.os].filter { !$0.isEmpty }.joined(separator: " · ")) }
                        }
                        if !g.fp.isEmpty {
                            LabeledContent("Host-Schlüssel") { Text(verbatim: g.fp).font(.caption).lineLimit(1).truncationMode(.middle) }
                        }
                        if g.sitzungen > 0 { LabeledContent("Offene Sitzungen") { Text(verbatim: "\(g.sitzungen)").foregroundStyle(.red) } }
                        if g.hostkeyFalsch {
                            Text("Der Server zeigt einen anderen Host-Schlüssel als bei der Kopplung: keine Verbindung. War das eine Neuinstallation, „Entfernen“ und neu koppeln.").foregroundStyle(.red)
                        }
                        if g.stand != "abbau" {
                            Toggle("Darf sich verbinden", isOn: Binding(get: { g.erlaubt }, set: { v in Task { await allow(g, v) } }))
                            Button("Shell oder Dateien im Panel öffnen") { panel() }.disabled(!g.online || g.hostkeyFalsch || !g.erlaubt)
                            Button("Trennen") { Task { await cut(g) } }.disabled(!g.online && g.sitzungen == 0)
                            Button("Entfernen", role: .destructive) { askRemove = g }
                        }
                    } footer: {
                        if g.stand == "abbau" { Text("Wird beim nächsten Kontakt abgebaut. Von Hand auf dem Server: sudo spark-anker entfernen") }
                    }
                }
                Section {
                    if servers.isEmpty { Text("Noch kein Server gekoppelt.").foregroundStyle(.secondary) }
                    Button("Neues System koppeln (im Panel)") { panel() }
                    Button("Alle trennen", role: .destructive) { askAll = true }
                } footer: {
                    Text(SparkAPI.way(String(localized: "Shell und Koppeln gibt es im Panel: ein Code oder Passkey entsperrt die Seite dort für eine Weile, Koppeln und Entfernen fragen jedes Mal; beim ersten Mal meldest du dich dort an wie im Browser. Die Seite: Fernzugang → Systeme.")))
                }
            }
        }
        .navigationTitle("Fernzugang")
        .refreshable { await load() }
        .task { await load() }
        .sheet(item: $open) { p in PanelPage(url: p.url).ignoresSafeArea() }
        .confirmationDialog("Jede Sitzung und jeden Anker jetzt trennen?", isPresented: $askAll, titleVisibility: .visible) {
            Button("Alle trennen", role: .destructive) { Task { await cutAll() } }
        }
        .confirmationDialog("Diesen Server entfernen? Der Schlüssel gilt sofort nicht mehr; der Anker baut auf dem Server alles ab, was er eingerichtet hat.",
                            isPresented: Binding(get: { askRemove != nil }, set: { if !$0 { askRemove = nil } }), titleVisibility: .visible) {
            Button("Entfernen", role: .destructive) { if let g = askRemove { Task { await remove(g) } } }
        }
    }

    private func panel() {
        if let url = SparkAPI.panelLink("go=fern") { open = PanelPlace(url: url) }
    }

    static func num(_ v: Any?) -> Int { (v as? NSNumber)?.intValue ?? 0 }
    private static func date(_ v: Any?) -> Date? {
        let s = (v as? NSNumber)?.doubleValue ?? 0
        return s > 0 ? Date(timeIntervalSince1970: s) : nil
    }
    static func word(_ g: FernServer) -> LocalizedStringKey {
        g.stand == "abbau" ? "wird abgebaut" : g.hostkeyFalsch ? "Host-Schlüssel falsch" : !g.erlaubt ? "gesperrt" : g.online ? "online" : "offline"
    }
    static func color(_ g: FernServer) -> Color {
        g.hostkeyFalsch ? .red : g.stand == "abbau" || !g.erlaubt ? .orange : g.online ? .green : .secondary
    }

    private func load() async {
        defer { loaded = true }
        do {
            d = try await AdminSession.shared.object("GET", "api/admin/fernzugang")
            servers = (d["geraete"] as? [[String: Any]] ?? []).prefix(20).compactMap { x in
                guard let id = x["id"] as? String, id.range(of: #"^g_[0-9a-f]{12}$"#, options: .regularExpression) != nil else { return nil }
                return FernServer(id: id, name: String((x["name"] as? String ?? "").prefix(40)), os: String((x["os"] as? String ?? "").prefix(40)),
                                  anker: String((x["anker"] as? String ?? "").prefix(20)), online: x["online"] as? Bool ?? false,
                                  onlineSeit: Self.date(x["online_seit"]), weg: Self.date(x["weg"]), zuletzt: Self.date(x["zuletzt"]),
                                  stand: x["stand"] as? String ?? "ok", erlaubt: x["erlaubt"] as? Bool ?? true,
                                  hostkeyFalsch: x["hostkey_falsch"] as? Bool ?? false, fp: String((x["fp"] as? String ?? "").prefix(80)),
                                  sitzungen: Self.num(x["sitzungen"]))
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func allow(_ g: FernServer, _ on: Bool) async {
        do { _ = try await AdminSession.shared.call("PUT", "api/admin/fernzugang/geraete/\(g.id)", body: ["erlaubt": on]); error = nil }
        catch { self.error = error.localizedDescription }
        await load()
    }

    private func cut(_ g: FernServer) async {
        do {
            _ = try await AdminSession.shared.call("POST", "api/admin/fernzugang/geraete/\(g.id)/trennen", body: [:])
            note = String(localized: "Getrennt. Der Anker kommt nach seiner Pause wieder, solange er sich verbinden darf.")
            error = nil
        } catch { self.error = error.localizedDescription }
        await load()
    }

    private func cutAll() async {
        do {
            let r = try await AdminSession.shared.object("POST", "api/admin/fernzugang/alle-trennen", body: [:])
            note = String(localized: "Getrennt: \(Self.num(r["n"]))")
            error = nil
        } catch { self.error = error.localizedDescription }
        await load()
    }

    private func remove(_ g: FernServer) async {
        do {
            _ = try await AdminSession.shared.call("DELETE", "api/admin/fernzugang/geraete/\(g.id)")
            note = String(localized: "Entfernt. Der Anker baut sich ab; ist er offline, beim nächsten Kontakt.")
            error = nil
        } catch { self.error = error.localizedDescription }
        await load()
    }
}
