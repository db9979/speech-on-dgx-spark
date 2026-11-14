import SwiftUI

/// Ich → Lautsprecher in the app (esp32.py, plan ios-nativ Paket 3, Dominik 2026-11-14): the profile's own speakers
/// with the same /api/profile/esp32 paths as the panel (iphone.THINGS["esp32"], open with the admin release of
/// „Eigene Lautsprecher“). Name, volume, microphone, own updates, the switch „Raum“, „Test“, „Netz prüfen“ and „Jetzt
/// aktualisieren“; the Spark checks the owner and the release on every path. Setting up a new speaker, removing one and
/// the code word stay in the browser.
@MainActor
final class LautsprecherModel: ObservableObject {
    @Published var d: [String: Any] = [:]
    @Published var loaded = false
    @Published var error: String?

    var devices: [[String: Any]] { d["devices"] as? [[String: Any]] ?? [] }

    func load() async {
        defer { loaded = true }
        guard let api = SparkAPI.current else { return }
        do { d = try await api.object("GET", "api/profile/esp32"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    /// a change of one speaker; the answer carries the whole list again
    func put(_ id: String, _ body: [String: Any]) async {
        guard let api = SparkAPI.current, Self.ok(id) else { return }
        do {
            let r = try await api.object("PUT", "api/profile/esp32/\(id)", body: body)
            if let list = r["devices"] { d["devices"] = list }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    static func ok(_ id: String) -> Bool { id.range(of: #"^d_[0-9a-f]{12}$"#, options: .regularExpression) != nil }
}

struct LautsprecherView: View {
    @StateObject private var m = LautsprecherModel()

    var body: some View {
        List {
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
            if !m.loaded && m.d.isEmpty {
                LadeZeilen(rows: 2)
            } else if m.d["enabled"] as? Bool == false || m.d["on"] as? Bool == false {
                Text(SparkAPI.way(String(localized: "Eigene Lautsprecher sind aus oder vom Admin für dich gesperrt.")))
            } else {
                Section {
                    if m.devices.isEmpty { Text("Noch kein Lautsprecher.").foregroundStyle(.secondary) }
                    ForEach(m.devices.indices, id: \.self) { i in
                        let x = m.devices[i]
                        NavigationLink { SpeakerView(m: m, id: x["id"] as? String ?? "") } label: { Self.row(x) }
                    }
                } footer: {
                    Text(SparkAPI.way(String(localized: "Einen neuen Lautsprecher richtest du im Browser im selben WLAN ein: Ich → Lautsprecher")))
                }
            }
        }
        .navigationTitle("Lautsprecher")
        .refreshable { await m.load() }
        .task { await m.load() }
    }

    @ViewBuilder static func row(_ x: [String: Any]) -> some View {
        HStack {
            VStack(alignment: .leading) {
                Text(verbatim: x["name"] as? String ?? "")
                Text(verbatim: x["board"] as? String ?? "").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if x["room"] as? Bool == true { Image(systemName: "ear").foregroundStyle(Theme.accent) }
            Circle().fill(x["online"] as? Bool == true ? Theme.ok : Color.secondary.opacity(0.4)).frame(width: 9, height: 9)
                .accessibilityLabel(x["online"] as? Bool == true ? Text("verbunden") : Text("nicht verbunden"))
        }
    }
}

/// One speaker: what the panel's card shows, as rows of the app.
struct SpeakerView: View {
    @ObservedObject var m: LautsprecherModel
    let id: String
    @State private var name = ""
    @State private var volume = 60.0
    @State private var msg: String?
    @State private var checks: [(Bool, String)] = []
    @State private var busy = false

    private var x: [String: Any]? { m.devices.first { $0["id"] as? String == id } }

    var body: some View {
        List {
            if let x {
                Section {
                    TextField("Name", text: $name).onSubmit { Task { await m.put(id, ["name": String(name.prefix(40))]) } }
                    LabeledContent("Verbunden") {
                        if x["online"] as? Bool == true { Text("jetzt") }
                        else if let s = x["seen"] as? Int { Text(Date(timeIntervalSince1970: TimeInterval(s)), format: .relative(presentation: .named)) }
                        else { Text("noch nie") }
                    }
                    LabeledContent("Board") { Text(verbatim: x["board"] as? String ?? "") }
                    LabeledContent("Firmware") {
                        Text(verbatim: x["fw"] as? String ?? "")
                        if x["newer"] as? Bool == true { Text("· neuere da").foregroundStyle(Theme.warnText) }
                    }
                }
                Section {
                    VStack(alignment: .leading) {
                        Text("Lautstärke")
                        Slider(value: $volume, in: 0...100, step: 5) { editing in
                            if !editing { Task { await m.put(id, ["volume": Int(volume)]) } }
                        }
                    }
                    Picker("Mikrofon", selection: Binding(get: { x["mic"] as? String ?? "normal" },
                                                          set: { v in Task { await m.put(id, ["mic": v]) } })) {
                        Text("empfindlicher").tag("high")
                        Text("normal").tag("normal")
                        Text("weniger empfindlich").tag("low")
                    }
                    Toggle("Updates von selbst", isOn: Binding(get: { x["auto"] as? Bool ?? true },
                                                              set: { v in Task { await m.put(id, ["auto": v]) } }))
                    if m.d["room"] as? Bool == true {
                        Toggle("Raum-Modus", isOn: Binding(get: { x["room"] as? Bool == true },
                                                         set: { v in Task { await m.put(id, ["room": v]) } }))
                    }
                } footer: {
                    if x["room_waits"] as? Bool == true { Text("Der Raum-Modus beginnt beim nächsten Weckwort.") }
                }
                Section {
                    Button("Test") { Task { await post("test") } }
                    Button("Netz prüfen") { Task { await post("check") } }
                    if x["newer"] as? Bool == true || x["update"] as? Bool == true {
                        Button("Jetzt aktualisieren") { Task { await post("update") } }
                    }
                    if busy { ProgressView() }
                    if let msg { Text(msg).foregroundStyle(.secondary) }
                    ForEach(checks.indices, id: \.self) { i in
                        Label { Text(verbatim: checks[i].1) } icon: {
                            Image(systemName: checks[i].0 ? "checkmark.circle.fill" : "xmark.octagon.fill")
                                .foregroundStyle(checks[i].0 ? Theme.ok : Theme.bad)
                        }
                    }
                } footer: {
                    Text(SparkAPI.way(String(localized: "Einrichten, Entfernen und die Raum-Einstellungen im Browser unter Ich → Lautsprecher; Stimme hier anlernen unter Stimme einlernen.")))
                }
            } else {
                Text("Diesen Lautsprecher gibt es nicht mehr.").foregroundStyle(.secondary)
            }
        }
        .navigationTitle(Text(verbatim: x?["name"] as? String ?? ""))
        .onAppear {
            name = x?["name"] as? String ?? ""
            volume = Double(x?["volume"] as? Int ?? 60)
        }
    }

    private func post(_ what: String) async {
        guard let api = SparkAPI.current, LautsprecherModel.ok(id) else { return }
        busy = true
        defer { busy = false }
        do {
            let r = try await api.object("POST", "api/profile/esp32/\(id)/\(what)", body: [:])
            switch what {
            case "test": msg = r["now"] as? Bool == true ? String(localized: "Er spricht jetzt einen Testsatz.") : String(localized: "Test vorgemerkt: beim nächsten Weckwort.")
            case "check":
                checks = (r["results"] as? [[String: Any]] ?? []).prefix(10).map { ($0["ok"] as? Bool == true, String(($0["text"] as? String ?? "").prefix(200))) }
                msg = nil
            default:
                if let list = r["devices"] { m.d["devices"] = list }
                msg = r["restarted"] as? Bool == true ? String(localized: "Er startet neu und holt das Update.") : String(localized: "Update beim nächsten Start.")
            }
        } catch { msg = error.localizedDescription }
    }
}
