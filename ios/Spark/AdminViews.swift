import LocalAuthentication
import SwiftUI
import UIKit

/// "Spark verwalten": the admin's part of the panel in the app. The app signs in like the browser, with the
/// admin password and the admin's code (the Spark wants both from a phone, and the profile's switch
/// "Spark verwalten in der App"). The login lives in memory only, in a session of its own without the
/// iPhone's key; closing the app or "Abmelden" ends it.
@MainActor
final class AdminSession: ObservableObject {
    static let shared = AdminSession()

    @Published private(set) var signedIn = false
    @Published var version = ""
    /// who is signed in: "main" (admin password) or a profile in its admin mode ("coadmin", "manager")
    @Published private(set) var role = "main"
    private var session = AdminSession.fresh()
    private var kept = Date.distantPast

    private static func fresh() -> URLSession {
        let c = URLSessionConfiguration.ephemeral
        c.httpCookieAcceptPolicy = .onlyFromMainDocumentDomain
        c.timeoutIntervalForRequest = 60
        return URLSession(configuration: c)
    }

    /// true: signed in; false: the Spark wants the code next
    func login(password: String, code: String?) async throws -> Bool {
        guard let base = Store.baseURL, let key = Store.key else { throw SparkError(message: String(localized: "Nicht gekoppelt.")) }
        var r = URLRequest(url: base.appendingPathComponent("api/login"))
        r.httpMethod = "POST"
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // the app's own key goes along only here: the Spark checks the profile's switch for this login
        r.setValue(key, forHTTPHeaderField: "X-Speech-Device")
        var body: [String: Any] = ["password": password]
        if let code { body["code"] = code }
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: r)
        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
        let d = SparkAPI.object(data)
        if statusCode == 200 && d["code"] as? Bool == true { return false }
        guard statusCode == 200 else {
            switch statusCode {
            case 401: throw SparkError(message: code == nil ? String(localized: "Falsches Passwort.") : String(localized: "Code falsch."))
            case 429: throw SparkError(message: String(localized: "Zu viele falsche Versuche, bitte später noch einmal."))
            default: throw SparkError(message: d["detail"] as? String ?? String(localized: "Fehler \(statusCode) vom Spark."))
            }
        }
        await signedInNow()
        return true
    }

    private func signedInNow() async {
        signedIn = true
        kept = Date()
        if let who = try? await object("GET", "api/whoami") {
            version = who["version"] as? String ?? ""
            let by = who["admin_by"] as? String ?? "main"
            role = ["coadmin", "manager"].contains(by) ? by : "main"
        }
    }

    /// "Mit meinem Profil anmelden": the profile's admin role with the iPhone's key and the profile's own code.
    func elevate(code: String) async throws {
        guard let base = Store.baseURL, let key = Store.key else { throw SparkError(message: String(localized: "Nicht gekoppelt.")) }
        var r = URLRequest(url: base.appendingPathComponent("api/admin/elevate"))
        r.httpMethod = "POST"
        // the app's own key goes along only here: the Spark checks the profile's role and switches for it
        r.setValue(key, forHTTPHeaderField: "X-Speech-Device")
        r.setValue(code, forHTTPHeaderField: "X-Speech-Code")
        let (data, response) = try await session.data(for: r)
        try SparkAPI.check(data, response)
        await signedInNow()
    }

    func logout() async {
        _ = try? await call("POST", role == "main" ? "api/logout" : "api/admin/elevate/end")
        role = "main"
        session.invalidateAndCancel()
        session = Self.fresh()
        signedIn = false
    }

    func call(_ method: String, _ path: String, query: [String: String] = [:], body: [String: Any]? = nil,
              code: String? = nil, timeout: TimeInterval = 60) async throws -> Data {
        guard let base = Store.baseURL else { throw SparkError(message: String(localized: "Nicht gekoppelt.")) }
        var c = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { c.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) } }
        var r = URLRequest(url: c.url!)
        r.httpMethod = method
        r.timeoutInterval = timeout
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        if let code { r.setValue(code, forHTTPHeaderField: "X-Speech-Code") }
        let (data, response) = try await session.data(for: r)
        // a profile's admin mode ends after 15 minutes without use: while used, renew it at most every 2 minutes
        if role != "main" && signedIn && path != "api/admin/elevate/keep" && Date().timeIntervalSince(kept) > 120 {
            kept = Date()
            Task { _ = try? await self.call("POST", "api/admin/elevate/keep") }
        }
        if (response as? HTTPURLResponse)?.statusCode == 401 {
            signedIn = false
            throw SparkError(message: String(localized: "Die Admin-Anmeldung ist abgelaufen. Bitte neu anmelden."))
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
    /// the profile's own admin role from the Spark ("coadmin", "manager" or "")
    var profileRole = ""
    @ObservedObject private var s = AdminSession.shared
    @State private var ask: CodeRequest?
    @State private var unlocked = false
    @State private var password = ""
    @State private var code = ""
    @State private var askCode = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        Form {
            if !unlocked {
                Section {
                    Button("Mit Face ID entsperren") { Task { unlocked = await AdminSession.unlock(String(localized: "Spark verwalten")) } }
                } footer: { Text("Danach meldest du dich mit dem Admin-Passwort und dem Code des Admins an, wie im Browser.") }
            } else if !s.signedIn {
                if !profileRole.isEmpty { profileLogin }
                login
            } else {
                Section {
                    NavigationLink("Monitoring") { StatusView() }
                    NavigationLink("Logs") { LogsView() }
                    if s.role != "manager" { NavigationLink("Prüfen") { ChecksView() } }
                } header: { Text("Zustand") }
                Section {
                    NavigationLink("Funktionen") { FeaturesView() }
                    NavigationLink("Personen und Geräte") { AdminProfilesView() }
                    if s.role != "manager" { NavigationLink("Sicherungen") { BackupsView() } }
                } header: { Text("Ändern") } footer: {
                    Text("Was einen Code braucht (neue PIN, Profil löschen), fragt danach. Sprachmodell, Engines und Ports bleiben im Browser.")
                }
                Section {
                    Button("Abmelden", role: .destructive) { Task { await s.logout() } }
                } footer: { Text("Die Anmeldung gilt nur, solange die App offen ist.") }
            }
        }
        .navigationTitle("Spark verwalten")
        .task { if !unlocked { unlocked = await AdminSession.unlock(String(localized: "Spark verwalten")) } }
        .codeAlert($ask)
    }

    private var profileLogin: some View {
        Section {
            Button("Mit meinem Profil anmelden") {
                ask = CodeRequest { c in
                    do { try await s.elevate(code: c); error = nil } catch { self.error = error.localizedDescription }
                }
            }
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
        } footer: {
            Text(profileRole == "manager" ? String(localized: "Als Verwalter: Monitoring, Logs, Funktionen, Personen und Geräte. Mit dem Code deines Profils.")
                                          : String(localized: "Als Mit-Admin, mit dem Code deines Profils. Nach 15 Minuten ohne Bedienung endet die Anmeldung."))
        }
    }

    private var login: some View {
        Section {
            SecureField("Admin-Passwort", text: $password).textContentType(.password)
            if askCode {
                TextField("Code aus der Authenticator-App", text: $code).keyboardType(.numberPad).textContentType(.oneTimeCode)
            }
            Button {
                Task { await signIn() }
            } label: { if busy { ProgressView() } else { Text("Anmelden") } }
            .disabled(busy || password.isEmpty || (askCode && code.count != 6))
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
        } header: { Text("Admin-Anmeldung") } footer: {
            Text("Geht nur mit dem zweiten Anmeldeschritt des Admins und mit „Spark verwalten in der App“ unter Ich → iPhone-App.")
        }
    }

    private func signIn() async {
        busy = true
        defer { busy = false }
        do {
            let done = try await s.login(password: password, code: askCode ? code : nil)
            if done { password = ""; code = ""; askCode = false; error = nil } else { askCode = true; error = nil }
        } catch { self.error = error.localizedDescription; code = "" }
    }
}

// ---------------------------------------------------------------- Zustand → Monitoring

struct StatusView: View {
    @State private var d: [String: Any] = [:]
    @State private var error: String?

    var body: some View {
        List {
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
            let alerts = d["alerts"] as? [[String: Any]] ?? []
            Section("Braucht dich") {
                if alerts.isEmpty { Label("Alles in Ordnung", systemImage: "checkmark.circle").foregroundStyle(.green) }
                ForEach(Array(alerts.enumerated()), id: \.offset) { _, a in
                    Label {
                        Text(verbatim: a["text"] as? String ?? "")
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(a["level"] as? String == "bad" ? .red : .orange)
                    }
                }
            }
            let sys = d["system"] as? [String: Any] ?? [:], gpu = d["gpu"] as? [String: Any] ?? [:]
            Section("Spark") {
                LabeledContent("Speicher frei") { Text(verbatim: Self.num(sys["mem_avail_gib"]) + " / " + Self.num(sys["mem_total_gib"]) + " GiB") }
                LabeledContent("CPU") { Text(verbatim: Self.num(sys["cpu"]) + " %") }
                LabeledContent("GPU") { Text(verbatim: Self.num(gpu["util"]) + " % · " + Self.num(gpu["temp"]) + " °C · " + Self.num(gpu["power"]) + " W") }
            }
            Section("Speech-Dienste") {
                ForEach(Self.services(d), id: \.0) { name, state in
                    LabeledContent(name) { Text(verbatim: state).foregroundStyle(Self.color(state)) }
                }
            }
        }
        .navigationTitle("Monitoring")
        .refreshable { await load() }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    private func load() async {
        do { d = try await AdminSession.shared.object("GET", "api/status"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    static func num(_ v: Any?) -> String {
        guard let n = (v as? NSNumber)?.doubleValue else { return "–" }
        return n == n.rounded() ? String(Int(n)) : String(format: "%.1f", n)
    }

    static func color(_ state: String) -> Color {
        ["active": .green, "activating": .orange, "failed": .red, "inactive": .secondary][state] ?? .primary
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
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
            if let l = last {
                Section("Letzter Fehler") {
                    Text(verbatim: (l["t"] as? String ?? "") + " · " + (l["msg"] as? String ?? "")).font(.footnote)
                    if let hint = l["hint"] as? [String: Any], let de = hint[Locale.current.language.languageCode?.identifier == "de" ? "de" : "en"] as? String {
                        Text(verbatim: de).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                ForEach(Array(rows.enumerated().reversed()), id: \.offset) { _, r in
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

    var body: some View {
        List {
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
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
                    if let e = r["error"] as? String { Text(verbatim: e).foregroundStyle(.red) }
                }
                Button("Vorrang prüfen") { Task { await run("api/vorrang") } }.disabled(vorrang["running"] as? Bool == true)
            } header: { Text("Vorrang für Sprache") } footer: { Text("Dauert etwa eine Minute.") }
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
            error = nil
        } catch { self.error = error.localizedDescription }
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
    @State private var error: String?

    /// a group of switches as the Spark sends it (features.py: names and groups, no list of its own in the app)
    struct SwitchGroup: Identifiable {
        let id: String
        let name: String
        let keys: [String]
    }

    var body: some View {
        Form {
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
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
            Text(verbatim: names[key] ?? key)
        }
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
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
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
                Text("Ein neues iPhone koppelt das Profil danach selbst unter Ich → iPhone-App.")
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
    /// the functions with an own switch the Spark allows, and whether this profile has them on (Wer darf was)
    @State private var funcs: [(key: String, name: String, on: Bool)] = []

    var body: some View {
        Form {
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if !role.isEmpty {
                LabeledContent("Admin-Rolle") { Text(role == "manager" ? String(localized: "Verwalter") : String(localized: "Mit-Admin")) }
            }
            Section {
                ForEach(funcs, id: \.key) { f in
                    Toggle(isOn: Binding(get: { f.on }, set: { v in Task { await setFunc(f.key, v) } })) { Text(verbatim: f.name) }
                }
                if funcs.isEmpty { Text("Keine Funktion mit eigenem Schalter an.").foregroundStyle(.secondary) }
            } header: { Text("Funktionen: \(funcsOn) von \(funcs.count) an") } footer: {
                Text("Die eigenen Schalter dieses Profils. Das Profil sieht und ändert sie selbst unter Ich.")
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
                return (key, name, cells[user.id] as? Bool ?? false)
            }
        } catch { self.error = error.localizedDescription }
    }

    private var funcsOn: Int { funcs.filter { $0.on }.count }

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
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
            Section {
                Button { Task { await create() } } label: { if busy { ProgressView() } else { Text("Jetzt sichern") } }.disabled(busy)
            } footer: { Text("Zurückspielen und Herunterladen gehen im Browser.") }
            Section {
                ForEach(items, id: \.name) { b in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(b.created, format: .dateTime.day().month().year().hour().minute())
                        Text(verbatim: ByteCountFormatter.string(fromByteCount: Int64(b.size), countStyle: .file)).font(.caption).foregroundStyle(.secondary)
                    }
                    .swipeActions { if s.role == "main" { Button("Löschen", role: .destructive) { Task { await remove(b.name) } } } }
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
