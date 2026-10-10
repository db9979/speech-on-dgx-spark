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
    private var session = AdminSession.fresh()

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
        signedIn = true
        if let who = try? await object("GET", "api/whoami") { version = who["version"] as? String ?? "" }
        return true
    }

    func logout() async {
        _ = try? await call("POST", "api/logout")
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
    @ObservedObject private var s = AdminSession.shared
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
                login
            } else {
                Section {
                    NavigationLink("Monitoring") { StatusView() }
                    NavigationLink("Logs") { LogsView() }
                    NavigationLink("Prüfen") { ChecksView() }
                } header: { Text("Zustand") }
                Section {
                    Button("Abmelden", role: .destructive) { Task { await s.logout() } }
                } footer: { Text("Die Anmeldung gilt nur, solange die App offen ist.") }
            }
        }
        .navigationTitle("Spark verwalten")
        .task { if !unlocked { unlocked = await AdminSession.unlock(String(localized: "Spark verwalten")) } }
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
