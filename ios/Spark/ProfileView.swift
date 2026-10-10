import SwiftUI

/// "Mein Profil": the profile's own voice, answers and "Von selbst", the same values as in the panel.
/// What the app may do and the tone are only shown; they change in the panel.
@MainActor
final class ProfileModel: ObservableObject {
    @Published var s: [String: Any] = [:]
    @Published var style: String?
    @Published var rights: [String: Bool] = [:]
    @Published var services: [String: Bool] = [:]
    /// conversation switches the admin allows (the profile's own switch matters only with it)
    @Published var adminAllows: [String: Bool] = [:]
    @Published var proactive = false
    @Published var voices: [String] = []
    @Published var loading = true
    @Published var error: String?
    @Published var sample = false

    func load() async {
        if let d = Demo.profile {
            show(d)
            voices = Demo.voices
            loading = false
            return
        }
        guard let api = SparkAPI.current else { return }
        do {
            show(try await api.profileSettings())
            voices = (try? await api.voices()) ?? []
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    private func show(_ d: [String: Any]) {
        s = d["settings"] as? [String: Any] ?? [:]
        style = d["style"] as? String
        rights = d["rights"] as? [String: Bool] ?? [:]
        services = d["services"] as? [String: Bool] ?? [:]
        proactive = (d["allow"] as? [String: Any])?["proactive"] as? Bool ?? false
        adminAllows = d["admin"] as? [String: Bool] ?? [:]
    }

    func set(_ key: String, _ value: Any) {
        s[key] = value
        Task {
            do { try await SparkAPI.current?.saveProfileSettings([key: value]); error = nil }
            catch { self.error = error.localizedDescription; await load() }
        }
    }

    func bool(_ key: String) -> Binding<Bool> {
        Binding(get: { self.s[key] as? Bool ?? false }, set: { self.set(key, $0) })
    }

    func text(_ key: String) -> String { s[key] as? String ?? "" }

    func int(_ key: String, _ fallback: Int) -> Int { (s[key] as? NSNumber)?.intValue ?? fallback }

    /// "HH:MM" as a time of day for the pickers
    static func date(_ hhmm: String, _ fallback: String) -> Date {
        let parts = (hhmm.isEmpty ? fallback : hhmm).split(separator: ":").compactMap { Int($0) }
        let h = parts.first ?? 7, m = parts.count > 1 ? parts[1] : 0
        return Calendar.current.date(bySettingHour: h, minute: m, second: 0, of: Date()) ?? Date()
    }

    static func hhmm(_ d: Date) -> String {
        let c = Calendar.current.dateComponents([.hour, .minute], from: d)
        return String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
    }

    func time(_ key: String, _ fallback: String) -> Binding<Date> {
        Binding(get: { Self.date(self.text(key), fallback) }, set: { self.set(key, Self.hhmm($0)) })
    }

    /// one end of the quiet time "22:00-07:00"
    func quiet(_ end: Int) -> Binding<Date> {
        Binding(get: {
            let p = self.text("pro_quiet").split(separator: "-").map(String.init)
            return Self.date(p.count == 2 ? p[end] : "", end == 0 ? "22:00" : "07:00")
        }, set: { d in
            var p = self.text("pro_quiet").split(separator: "-").map(String.init)
            if p.count != 2 { p = ["22:00", "07:00"] }
            p[end] = Self.hhmm(d)
            self.set("pro_quiet", p.joined(separator: "-"))
        })
    }

    /// says a short sentence in the saved voice
    func listen(_ audio: AudioEngine) {
        guard let api = SparkAPI.current, !sample else { return }
        sample = true
        Task {
            do { for try await pcm in api.say(String(localized: "Hallo, so klinge ich.")) { audio.play(pcm) } } catch {}
            sample = false
        }
    }
}

struct ProfileView: View {
    @EnvironmentObject var talk: Conversation
    @StateObject private var m = ProfileModel()

    var body: some View {
        Form {
            if m.loading {
                ProgressView()
            } else {
                if let e = m.error {
                    Section { Text(verbatim: e).foregroundStyle(.red) }
                }
                voice
                answers
                if m.proactive { byItself }
                rights
            }
        }
        .navigationTitle("Mein Profil")
        .task { await m.load() }
    }

    private var voice: some View {
        Section {
            Picker("Stimme", selection: Binding(get: { m.text("voice") }, set: { m.set("voice", $0) })) {
                Text("Standard").tag("")
                ForEach(m.voices, id: \.self) { Text(verbatim: $0).tag($0) }
            }
            VStack(alignment: .leading) {
                LabeledContent("Sprechtempo") {
                    Text(verbatim: String(format: "%.2f", (m.s["speed"] as? NSNumber)?.doubleValue ?? 1.0))
                }
                Slider(value: Binding(get: { (m.s["speed"] as? NSNumber)?.doubleValue ?? 1.0 },
                                      set: { m.s["speed"] = (($0 * 20).rounded() / 20) }),
                       in: 0.7...1.4, step: 0.05, onEditingChanged: { editing in
                    if !editing { m.set("speed", (m.s["speed"] as? NSNumber)?.doubleValue ?? 1.0) }
                })
            }
            Button(m.sample ? LocalizedStringKey("Spricht …") : LocalizedStringKey("Probehören")) { m.listen(talk.audio) }.disabled(m.sample)
        } header: { Text("Stimme") }
    }

    private var answers: some View {
        Section {
            Picker("Antwortlänge", selection: Binding(get: { m.text("length") }, set: { m.set("length", $0) })) {
                Text("Kurz").tag("short")
                Text("Normal").tag("normal")
                Text("Ausführlich").tag("long")
            }
            // with "Mein Alltag" (Ich → iPhone-App): the conversation switches of the panel
            if m.s["learn"] != nil { Toggle("Aus Gesprächen lernen", isOn: m.bool("learn")) }
            if m.s["daily"] != nil { Toggle("Jeden Tag neues Gespräch", isOn: m.bool("daily")) }
            if m.s["fix_learn"] != nil && m.adminAllows["fix_learn"] == true { Toggle("Aus Korrekturen lernen", isOn: m.bool("fix_learn")) }
            if m.s["tool_think"] != nil && m.adminAllows["tool_think"] == true { Toggle("Bei Werkzeugen nachdenken", isOn: m.bool("tool_think")) }
            if m.s["route"] != nil && m.adminAllows["route"] == true { Toggle("Gezielte Werkzeugwahl", isOn: m.bool("route")) }
            if let style = m.style {
                LabeledContent("Wünsche zum Ton") { Text(verbatim: style.isEmpty ? "–" : style).foregroundStyle(.secondary) }
            }
        } header: { Text("Antworten") } footer: {
            if m.style != nil { Text("Die Wünsche zum Ton änderst du im Panel, weil sie dem Sprachmodell gesagt werden.") }
        }
    }

    private var byItself: some View {
        Section {
            Toggle("Von selbst sprechen", isOn: m.bool("pro_on"))
            if m.s["pro_on"] as? Bool == true {
                DatePicker("Ruhe ab", selection: m.quiet(0), displayedComponents: .hourAndMinute)
                DatePicker("Ruhe bis", selection: m.quiet(1), displayedComponents: .hourAndMinute)
                Stepper("Höchstens \(m.int("pro_max", 6)) am Tag", value: Binding(get: { m.int("pro_max", 6) }, set: { m.set("pro_max", $0) }), in: 1...30)
                Toggle("Termine", isOn: m.bool("pro_events"))
                if m.s["pro_events"] as? Bool == true {
                    Picker("Vorlauf", selection: Binding(get: { m.int("pro_lead", 20) }, set: { m.set("pro_lead", $0) })) {
                        ForEach([5, 10, 15, 20, 30, 45, 60], id: \.self) { Text("\($0) Minuten").tag($0) }
                    }
                }
                service("Wetter", "pro_weather", "wx_on")
                if m.s["pro_weather"] as? Bool == true && m.services["wx_on"] == true {
                    TextField("Ort", text: Binding(get: { m.text("pro_place") }, set: { m.s["pro_place"] = $0 }))
                        .onSubmit { m.set("pro_place", String(m.text("pro_place").prefix(60))) }
                    DatePicker("Wetter um", selection: m.time("pro_weather_at", "18:00"), displayedComponents: .hourAndMinute)
                }
                service("Pakete", "pro_parcel", "par_on")
                service("Geburtstage", "pro_bday", "con_on")
                service("Bus und Bahn", "pro_transit", "transit_on")
                Toggle("Begrüßung", isOn: m.bool("pro_greet"))
                Toggle("Mails", isOn: m.bool("pro_mail"))
            }
            Toggle("Morgenrunde", isOn: Binding(get: { !m.text("briefing_at").isEmpty },
                                                 set: { m.set("briefing_at", $0 ? "07:00" : "") }))
            if !m.text("briefing_at").isEmpty {
                DatePicker("Morgenrunde um", selection: m.time("briefing_at", "07:00"), displayedComponents: .hourAndMinute)
            }
        } header: { Text("Von selbst") } footer: {
            Text("Ausgegraute Themen schaltest du zuerst im Panel ein.")
        }
    }

    private func service(_ title: LocalizedStringKey, _ key: String, _ needs: String) -> some View {
        Toggle(title, isOn: m.bool(key)).disabled(m.services[needs] != true)
    }

    private var rights: some View {
        Section {
            right("Smart Home", "app_ha")
            right("Smart Home im Auto", "app_car_ha")
            right("Route und Anrufe", "app_act")
            right("Dauerhaft zuhören", "app_listen")
            right("Meldungen aufs iPhone", "app_push")
            right("Dokumente ablegen", "app_docs")
            if let base = Store.baseURL {
                Link("Panel öffnen", destination: base)
            }
        } header: { Text("Was die App darf") } footer: {
            Text("Ändern im Panel unter Ich → iPhone-App.")
        }
    }

    private func right(_ title: LocalizedStringKey, _ key: String) -> some View {
        LabeledContent(title) {
            Image(systemName: m.rights[key] == true ? "checkmark.circle.fill" : "xmark.circle")
                .foregroundStyle(m.rights[key] == true ? .green : .secondary)
        }
    }
}
