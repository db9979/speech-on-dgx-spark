import AVFoundation
import SwiftUI

/// Mein Profil → Gespräch (plan ios-nativ Paket 4, Dominik 2026-11-14): the rest of the panel's Ich → Gespräch. The
/// Spark sends only the rows the admin released for this profile (iphone.TALK); a row it does not send is not shown,
/// and it saves only those. The allowed values of a list come from the Spark (`choices`), the words for them stay here
/// like in the panel.
struct GespraechView: View {
    @ObservedObject var m: ProfileModel

    var body: some View {
        Form {
            if let e = m.error { Section { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) } }
            Section {
                pick("follow", "Rückfrage ohne Weckwort", ["0": "aus", "4": "4 Sekunden", "6": "6 Sekunden", "8": "8 Sekunden", "10": "10 Sekunden"])
                toggle("echo", "Eigene Stimme überhören")
                toggle("auto", "Bei Stille beenden")
                toggle("turn", "Natürlicher Sprecherwechsel")
                toggle("live", "Live-Transkript")
                pick("barge_level", "Empfindlichkeit beim Ins-Wort-Fallen", ["low": "gering", "mid": "mittel", "high": "hoch"])
            } header: { Text("Zuhören") }
            Section {
                if m.stimmdesign { NavigationLink("Eigene Stimme") { StimmdesignView(m: m) } }
                toggle("voice_tips", "Tipps beim Sprechen")
                toggle("talk_hints", "Natürliches Gespräch")
                toggle("quelle_sagen", "Quelle ansagen")
                toggle("timing", "Zeiten anzeigen")
            } header: { Text("Antwort") }
            if has("chat_receipts") || has("msg_speaker") || has("msg_all") {
                Section {
                    toggle("chat_receipts", "Lesebestätigung")
                    toggle("chat_push_text", "Text in der Mitteilung")
                    pick("msg_speaker", "Neue Nachrichten auf meinem Lautsprecher", ["off": "nichts sagen", "hint": "nur sagen, von wem", "text": "von wem, Text auf Wunsch vorlesen"])
                    toggle("msg_all", "Nachricht an alle")
                } header: { Text("Chats") }
            }
            Section {
                toggle("devup_night", "Meine Lautsprecher nachts aktualisieren")
                toggle("rate_back", "Sagen, wenn es behoben ist")
                toggle("unklar_anon", "Unklare Fragen anonym zur Verbesserung")
            } header: { Text("Weiteres") } footer: {
                Text(SparkAPI.way(String(localized: "Was hier fehlt, hat der Admin nicht freigegeben. Ton, Rollen, wer mir schreiben darf und mein Name im Anfragen-Log: im Browser unter Ich → Gespräch.")))
            }
        }
        .navigationTitle("Gespräch")
    }

    private func has(_ key: String) -> Bool { m.s[key] != nil }

    @ViewBuilder private func toggle(_ key: String, _ title: LocalizedStringKey) -> some View {
        if has(key) { Toggle(title, isOn: m.bool(key)) }
    }

    /// a list row: only the values the Spark allows, in its order; a value without a word here shows as it is
    @ViewBuilder private func pick(_ key: String, _ title: LocalizedStringKey, _ words: [String: LocalizedStringKey]) -> some View {
        if has(key) {
            Picker(title, selection: Binding(get: { "\(m.s[key] ?? "")" }, set: { m.set(key, $0) })) {
                ForEach(m.choices[key] ?? [], id: \.self) { v in
                    if let w = words[v] { Text(w).tag(v) } else { Text(verbatim: v).tag(v) }
                }
            }
        }
    }
}

/// Eigene Stimme (stimmdesign.py): the 20 fixed voices and the own ones to hear and pick, a new one from the fields and
/// own words („Probe“, then „Übernehmen“ with a name) and deleting an own one. The same paths as the panel
/// (iphone.THINGS["stimmdesign"]); the Spark checks the release, the day's probes and the names.
struct StimmdesignView: View {
    @ObservedObject var m: ProfileModel
    @State private var d: [String: Any] = [:]
    @State private var error: String?
    @State private var felder: [String: String] = [:]
    @State private var worte = ""
    @State private var name = ""
    @State private var probe = false
    @State private var busy = false
    @State private var player: AVAudioPlayer?

    private var fertig: [[String: Any]] { d["fertig"] as? [[String: Any]] ?? [] }
    private var eigene: [[String: Any]] { d["eigene"] as? [[String: Any]] ?? [] }
    private var wahl: String { m.text("voice") }
    private func num(_ k: String) -> Int { (d[k] as? NSNumber)?.intValue ?? 0 }

    var body: some View {
        Form {
            if let e = error { Section { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) } }
            if !eigene.isEmpty {
                Section("Meine Stimmen") {
                    ForEach(eigene.indices, id: \.self) { i in
                        let x = eigene[i], id = x["id"] as? String ?? ""
                        row(Text(verbatim: x["name"] as? String ?? id), id: id, ready: true)
                            .swipeActions { Button(role: .destructive) { Task { await delete(id) } } label: { Label("Löschen", systemImage: "trash") } }
                    }
                }
            }
            Section("Fertige Stimmen") {
                ForEach(fertig.indices, id: \.self) { i in
                    let x = fertig[i], id = x["id"] as? String ?? ""
                    row(Text(verbatim: FeaturesView.pick([x["de"] as? String ?? id, x["en"] as? String ?? id]) ?? id), id: id, ready: x["da"] as? Bool == true)
                }
            }
            if d["design"] as? Bool == true {
                Section {
                    ForEach(fieldKeys, id: \.self) { k in
                        Picker(Self.label(k), selection: Binding(get: { felder[k] ?? "" }, set: { felder[k] = $0 })) {
                            Text("egal").tag("")
                            ForEach(options(k), id: \.0) { Text(verbatim: $0.1).tag($0.0) }
                        }
                    }
                    TextField("Eigene Worte (freiwillig)", text: $worte)
                    Button(probe ? LocalizedStringKey("Neu würfeln") : LocalizedStringKey("Probe anhören")) { Task { await makeProbe() } }.disabled(busy)
                    if probe {
                        TextField("Name der Stimme", text: $name)
                        Button("Übernehmen") { Task { await take() } }.disabled(busy || name.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    if busy { ProgressView() }
                } header: { Text("Neue Stimme gestalten") } footer: {
                    Text("Heute \(num("proben")) von \(num("proben_max")) Proben. Höchstens \(num("max")) eigene Stimmen.")
                }
            } else if !d.isEmpty {
                Section { Text("Neue Stimmen gestalten geht, sobald VoiceDesign auf dem Spark läuft.").foregroundStyle(.secondary) }
            }
        }
        .navigationTitle("Eigene Stimme")
        .task { await load() }
    }

    private var fieldKeys: [String] { (d["felder"] as? [String: Any] ?? [:]).keys.sorted { Self.order($0) < Self.order($1) } }

    private func options(_ k: String) -> [(String, String)] {
        ((d["felder"] as? [String: Any])?[k] as? [[String]] ?? []).compactMap { y in
            y.count == 3 ? (y[0], FeaturesView.pick([y[1], y[2]]) ?? y[0]) : nil
        }
    }

    static func order(_ k: String) -> Int { ["geschlecht", "alter", "tonlage", "tempo", "art"].firstIndex(of: k) ?? 99 }

    static func label(_ k: String) -> LocalizedStringKey {
        switch k {
        case "geschlecht": return "Geschlecht"
        case "alter": return "Alter"
        case "tonlage": return "Tonlage"
        case "tempo": return "Tempo"
        case "art": return "Art"
        default: return LocalizedStringKey(k)
        }
    }

    @ViewBuilder private func row(_ title: Text, id: String, ready: Bool) -> some View {
        HStack {
            Button { m.set("voice", id) } label: {
                HStack {
                    title.foregroundStyle(ready ? .primary : .secondary)
                    Spacer()
                    if wahl == id { Image(systemName: "checkmark").foregroundStyle(Theme.accent) }
                }
            }.disabled(!ready)
            if ready {
                Button { Task { await hear(id) } } label: { Image(systemName: "play.circle") }
                    .buttonStyle(.borderless).accessibilityLabel(Text("Anhören"))
            }
        }
    }

    private func load() async {
        guard let api = SparkAPI.current else { return }
        do { d = try await api.object("GET", "api/stimmdesign"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    /// the WAV of a request (▶ or Probe), played here; the Spark's message on an error
    private func wav(_ method: String, _ path: String, _ body: [String: Any]? = nil) async -> Data? {
        guard let api = SparkAPI.current else { return nil }
        var r = api.request(path, method: method)
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        r.timeoutInterval = 120
        do {
            let (data, response) = try await URLSession.shared.data(for: r)
            try SparkAPI.check(data, response)
            error = nil
            return data
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    private func play(_ data: Data) {
        player = try? AVAudioPlayer(data: data, fileTypeHint: AVFileType.wav.rawValue)
        player?.play()
    }

    private func hear(_ id: String) async {
        guard id.range(of: #"^[a-z0-9-]{3,40}$"#, options: .regularExpression) != nil,
              let data = await wav("GET", "api/stimmdesign/hoeren/\(id)") else { return }
        play(data)
    }

    private func makeProbe() async {
        busy = true
        defer { busy = false }
        if let data = await wav("POST", "api/stimmdesign/probe", ["felder": felder.filter { !$0.value.isEmpty }, "worte": String(worte.prefix(200))]) {
            probe = true
            play(data)
            await load()
        }
    }

    private func take() async {
        guard let api = SparkAPI.current else { return }
        busy = true
        defer { busy = false }
        do {
            let r = try await api.object("POST", "api/stimmdesign/eigene", body: ["name": String(name.trimmingCharacters(in: .whitespaces).prefix(40))])
            if let id = r["id"] as? String { m.s["voice"] = id }
            probe = false
            name = ""
            error = nil
            await load()
        } catch { self.error = error.localizedDescription }
    }

    private func delete(_ id: String) async {
        guard let api = SparkAPI.current, id.range(of: #"^eigen-[0-9a-f]{16}$"#, options: .regularExpression) != nil else { return }
        do {
            _ = try await api.call("DELETE", "api/stimmdesign/eigene/\(id)")
            if wahl == id { m.s["voice"] = "" }
            await load()
        } catch { self.error = error.localizedDescription }
    }
}
