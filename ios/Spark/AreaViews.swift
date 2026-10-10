import AVFoundation
import SwiftUI

/// A step the Spark confirms with a fresh code from the authenticator app (each code only once).
struct CodeRequest: Identifiable {
    let id = UUID()
    let run: (String) async -> Void
}

struct CodeAlert: ViewModifier {
    @Binding var request: CodeRequest?
    @State private var code = ""

    func body(content: Content) -> some View {
        content.alert("Code aus der Authenticator-App", isPresented: Binding(get: { request != nil }, set: { if !$0 { request = nil } })) {
            TextField("123456", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
            Button("Bestätigen") {
                let r = request
                let c = String(code.filter(\.isNumber).prefix(6))
                code = ""
                Task { await r?.run(c) }
            }
            Button("Abbrechen", role: .cancel) { code = "" }
        } message: {
            Text("Der Code gilt nur einmal.")
        }
    }
}

extension View {
    func codeAlert(_ request: Binding<CodeRequest?>) -> some View { modifier(CodeAlert(request: request)) }
}

/// A switch of the profile's own settings (PUT /api/iphone/settings; the Spark decides which the app may set).
struct SettingToggle: View {
    let title: LocalizedStringKey
    let key: String
    @Binding var settings: [String: Bool]
    @Binding var error: String?

    var body: some View {
        Toggle(title, isOn: Binding(get: { settings[key] ?? false }, set: { v in
            settings[key] = v
            Task {
                do { _ = try await SparkAPI.current?.call("PUT", "api/iphone/settings", body: [key: v]); error = nil }
                catch { self.error = error.localizedDescription; settings[key] = !v }
            }
        }))
    }
}

// MARK: - Stimme einlernen

/// Speaker recognition: the profile's voice through the iPhone's microphone, and "Stimme hier anlernen" at
/// one of the profile's speakers. Both need a fresh code: a voice print decides whose "Ja" counts.
@MainActor
final class VoiceModel: ObservableObject {
    @Published var samples = 0
    @Published var enabled = false
    @Published var speakers: [(id: String, name: String, online: Bool)] = []
    @Published var recording = false
    @Published var seconds = 0
    @Published var wav: Data?
    @Published var busy = false
    @Published var note: String?
    @Published var error: String?
    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private let file = FileManager.default.temporaryDirectory.appendingPathComponent("stimme.wav")

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/voice")
            samples = (d["samples"] as? NSNumber)?.intValue ?? 0
            enabled = d["enabled"] as? Bool ?? false
            let e = try? await api.object("GET", "api/profile/esp32")
            speakers = ((e?["devices"] as? [[String: Any]]) ?? []).compactMap { x in
                guard let id = x["id"] as? String, SparkAPI.devId(id) else { return nil }
                return (id, String((x["name"] as? String ?? "").prefix(40)), x["online"] as? Bool ?? false)
            }
        } catch { self.error = error.localizedDescription }
    }

    func start() async {
        guard await AVAudioApplication.requestRecordPermission() else {
            error = String(localized: "Die App darf das Mikrofon nicht benutzen (Einstellungen → Spark).")
            return
        }
        do {
            let s = AVAudioSession.sharedInstance()
            try s.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])   // the iPhone's own microphone, as at the speaker
            try s.setActive(true)
            let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
                                           AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
            let r = try AVAudioRecorder(url: file, settings: settings)
            guard r.record(forDuration: 60) else { throw SparkError(message: String(localized: "Aufnahme ging nicht.")) }
            recorder = r
            wav = nil
            seconds = 0
            recording = true
            error = nil
            timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.recording else { return }
                    self.seconds += 1
                    if self.recorder?.isRecording != true { self.stop() }
                }
            }
        } catch { self.error = error.localizedDescription }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        recorder?.stop()
        recorder = nil
        recording = false
        wav = try? Data(contentsOf: file)
        try? FileManager.default.removeItem(at: file)
        if seconds < 5 {
            wav = nil
            error = String(localized: "Zu kurz. Bitte alle drei Sätze vorlesen.")
        }
    }

    func send(code: String) async {
        guard let api = SparkAPI.current, let wav else { return }
        busy = true
        defer { busy = false }
        do {
            samples = try await api.addVoice(wav: wav, code: code)
            self.wav = nil
            note = String(localized: "Gespeichert. Mehr Aufnahmen machen die Erkennung sicherer.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func forget() async {
        do {
            _ = try await SparkAPI.current?.call("DELETE", "api/profile/voice")
            samples = 0
        } catch { self.error = error.localizedDescription }
    }

    func teach(_ id: String, code: String) async {
        guard SparkAPI.devId(id) else { return }
        do {
            let r = try await SparkAPI.current?.object("POST", "api/profile/esp32/\(id)/voice", body: [:], code: code)
            note = r?["now"] as? Bool == true ? String(localized: "Der Lautsprecher fragt jetzt nach den Sätzen.")
                                               : String(localized: "Vorgemerkt: beim nächsten Weckwort oder Knopfdruck.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct VoiceView: View {
    @StateObject private var m = VoiceModel()
    @State private var ask: CodeRequest?
    @State private var confirmForget = false

    static let sentences = [
        String(localized: "Der Herbstwind treibt bunte Blätter über die stille Straße, und irgendwo bellt ein Hund."),
        String(localized: "Kannst du mir bitte sagen, wie das Wetter morgen wird und ob ich einen Schirm brauche?"),
        String(localized: "Zweiundvierzig Äpfel, sieben Birnen und ein Korb voller Pflaumen stehen auf dem Küchentisch."),
    ]

    var body: some View {
        Form {
            if !m.enabled {
                Text("Die Sprechererkennung ist aus (Admin: Einstellungen → Funktionen).").foregroundStyle(.secondary)
            }
            Section {
                LabeledContent("Aufnahmen", value: "\(m.samples)")
                if m.recording {
                    ForEach(Self.sentences, id: \.self) { Text(verbatim: $0).font(.callout) }
                    Button { m.stop() } label: { Label("Fertig (\(m.seconds) s)", systemImage: "stop.circle.fill") }
                } else if m.wav != nil {
                    Button {
                        ask = CodeRequest { code in await m.send(code: code) }
                    } label: { if m.busy { ProgressView() } else { Label("Aufnahme speichern", systemImage: "checkmark.circle") } }
                    .disabled(m.busy)
                    Button("Verwerfen", role: .destructive) { m.wav = nil }
                } else {
                    Button { Task { await m.start() } } label: {
                        Label(m.samples > 0 ? String(localized: "Weitere Aufnahme") : String(localized: "Stimme einlernen"), systemImage: "mic.circle")
                    }
                    .disabled(!m.enabled)
                }
                if m.samples > 0 && !m.recording {
                    Button("Gespeicherte Stimme löschen", role: .destructive) { confirmForget = true }
                }
            } header: { Text("Mit dem iPhone") } footer: {
                Text("Nach dem Start erscheinen drei Sätze. Lies sie in normaler Lautstärke vor und tippe auf Fertig. Gespeichert wird erst mit dem Code aus der Authenticator-App.")
            }
            if !m.speakers.isEmpty {
                Section {
                    ForEach(m.speakers, id: \.id) { s in
                        HStack {
                            Text(verbatim: s.name)
                            if !s.online { Text("nicht verbunden").font(.caption).foregroundStyle(.secondary) }
                            Spacer()
                            Button("Anlernen") { ask = CodeRequest { code in await m.teach(s.id, code: code) } }
                                .buttonStyle(.bordered)
                                .disabled(!m.enabled)
                        }
                    }
                } header: { Text("Stimme hier anlernen") } footer: {
                    Text("Der Lautsprecher bittet dich um fünf Sätze, mit seinem eigenen Mikrofon. So erkennt er dich dort sicherer.")
                }
            }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
        }
        .navigationTitle("Stimme einlernen")
        .task { await m.load() }
        .onDisappear { if m.recording { m.stop() } }
        .codeAlert($ask)
        .confirmationDialog("Gespeicherte Stimme löschen?", isPresented: $confirmForget, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) { Task { await m.forget() } }
        }
    }
}

// MARK: - Von selbst

struct Job: Identifiable, Hashable {
    let id: String
    let task: String
    let state: String
    let created: Date
    let summary: String
    let error: String
}

@MainActor
final class AutoModel: ObservableObject {
    @Published var settings: [String: Bool] = [:]
    @Published var place = ""
    @Published var placeInput = ""
    @Published var choices: [[String: Any]] = []
    @Published var home = ""
    @Published var stopInput = ""
    @Published var stops: [(id: String, name: String)] = []
    @Published var parcels: [String] = []
    @Published var parcelNote: String?
    @Published var jobs: [Job] = []
    @Published var rooms: [ListeningRoom] = []
    @Published var sample: String?
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        if let s = try? await api.object("GET", "api/iphone/settings") {
            settings = ((s["settings"] as? [String: Any]) ?? [:]).compactMapValues { $0 as? Bool }
        }
        if let w = try? await api.object("GET", "api/profile/weather") {
            place = (w["place"] as? [String: Any])?["name"] as? String ?? ""
        }
        if let t = try? await api.object("GET", "api/profile/transit") {
            home = (t["home"] as? [String: Any])?["name"] as? String ?? ""
        }
        do {
            let p = try await api.object("GET", "api/profile/parcels")
            parcels = (p["lines"] as? [String] ?? []).prefix(30).map { String($0.prefix(300)) }
            let errors = p["errors"] as? [String] ?? []
            parcelNote = errors.isEmpty ? nil : errors.joined(separator: "\n")
        } catch { parcelNote = error.localizedDescription }
        if let a = try? await api.object("GET", "api/profile/agent") {
            jobs = (a["jobs"] as? [[String: Any]] ?? []).prefix(30).compactMap { x in
                guard let id = x["id"] as? String, SparkAPI.id(id) else { return nil }
                return Job(id: id, task: String((x["task"] as? String ?? "").prefix(300)), state: x["state"] as? String ?? "",
                           created: Date(timeIntervalSince1970: (x["created"] as? NSNumber)?.doubleValue ?? 0),
                           summary: String((x["summary"] as? String ?? "").prefix(2000)), error: String((x["error"] as? String ?? "").prefix(500)))
            }
        }
        rooms = (try? await api.rooms()) ?? []
    }

    func setPlace(pick: [String: Any]? = nil) async {
        guard let api = SparkAPI.current else { return }
        var body: [String: Any] = ["place": String(placeInput.prefix(80))]
        if let pick { body["pick"] = pick }
        do {
            let d = try await api.object("PUT", "api/profile/weather", body: body)
            place = (d["place"] as? [String: Any])?["name"] as? String ?? place
            choices = Array((d["choices"] as? [[String: Any]] ?? []).prefix(8))
            sample = (d["sample"] as? String).flatMap { $0.isEmpty ? nil : String($0.prefix(1000)) }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func findStops() async {
        do {
            let d = try await SparkAPI.current?.object("POST", "api/profile/transit/find", body: ["q": String(stopInput.prefix(80))])
            stops = ((d?["stops"] as? [[String: Any]]) ?? []).prefix(10).compactMap { x in
                guard let id = x["id"] as? String else { return nil }
                return (id, x["name"] as? String ?? id)
            }
            error = stops.isEmpty ? String(localized: "Keine Haltestelle gefunden.") : nil
        } catch { self.error = error.localizedDescription }
    }

    func setHome(_ id: String, _ name: String) async {
        do {
            let d = try await SparkAPI.current?.object("PUT", "api/profile/transit", body: ["home": ["id": id, "name": name]])
            home = (d?["home"] as? [String: Any])?["name"] as? String ?? name
            stops = []
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func test(_ path: String) async {
        do {
            let d = try await SparkAPI.current?.object("POST", path, body: [:])
            sample = (d?["text"] as? String).map { String($0.prefix(1000)) }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func cancel(_ j: Job) async {
        do { _ = try await SparkAPI.current?.call("POST", "api/profile/agent/jobs/\(j.id)/cancel"); await load() }
        catch { self.error = error.localizedDescription }
    }

    func extend(_ r: ListeningRoom) async {
        do {
            _ = try await SparkAPI.current?.call("POST", "api/room/extend", body: ["key": r.id, "mins": 30])
            rooms = (try? await SparkAPI.current?.rooms()) ?? rooms
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct AutoView: View {
    @StateObject private var m = AutoModel()

    var body: some View {
        Form {
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
            if let s = m.sample { Section { Text(verbatim: s) } header: { Text("Antwort des Spark") } }
            Section {
                SettingToggle(title: "Wetter", key: "wx_on", settings: $m.settings, error: $m.error)
                if m.settings["wx_on"] == true {
                    if !m.place.isEmpty { LabeledContent("Ort", value: m.place) }
                    HStack {
                        TextField("Ort, z. B. Freiburg", text: $m.placeInput)
                        Button("Setzen") { Task { await m.setPlace() } }.disabled(m.placeInput.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    ForEach(Array(m.choices.enumerated()), id: \.offset) { _, c in
                        Button { Task { await m.setPlace(pick: c) } } label: { Text(verbatim: c["name"] as? String ?? "?") }
                    }
                    if !m.place.isEmpty { Button("Wetter ausprobieren") { Task { await m.test("api/profile/weather/test") } } }
                }
            } header: { Text("Wetter") }
            Section {
                SettingToggle(title: "Pakete aus E-Mails", key: "par_on", settings: $m.settings, error: $m.error)
                if m.settings["par_on"] == true {
                    if m.parcels.isEmpty && m.parcelNote == nil { Text("Keine Pakete unterwegs.").foregroundStyle(.secondary) }
                    ForEach(m.parcels, id: \.self) { Text(verbatim: $0).font(.callout) }
                    if let n = m.parcelNote { Text(verbatim: n).font(.caption).foregroundStyle(.secondary) }
                }
            } header: { Text("Pakete") }
            Section {
                SettingToggle(title: "Bus und Bahn", key: "transit_on", settings: $m.settings, error: $m.error)
                if m.settings["transit_on"] == true {
                    if !m.home.isEmpty { LabeledContent("Haltestelle", value: m.home) }
                    HStack {
                        TextField("Haltestelle suchen", text: $m.stopInput)
                        Button("Suchen") { Task { await m.findStops() } }.disabled(m.stopInput.trimmingCharacters(in: .whitespaces).count < 2)
                    }
                    ForEach(m.stops, id: \.id) { s in
                        Button { Task { await m.setHome(s.id, s.name) } } label: { Text(verbatim: s.name) }
                    }
                    if !m.home.isEmpty { Button("Abfahrten ausprobieren") { Task { await m.test("api/profile/transit/test") } } }
                }
            } header: { Text("Bus und Bahn") }
            Section {
                SettingToggle(title: "Aufträge", key: "agent_on", settings: $m.settings, error: $m.error)
                ForEach(m.jobs) { j in
                    NavigationLink { JobView(job: j) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: j.task).lineLimit(2)
                            HStack {
                                Text(verbatim: Self.state(j.state))
                                Text(j.created, format: .dateTime.day().month().hour().minute())
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .swipeActions {
                        if ["queued", "running"].contains(j.state) {
                            Button("Stoppen", role: .destructive) { Task { await m.cancel(j) } }
                        }
                    }
                }
            } header: { Text("Aufträge") } footer: { Text("Neue Aufträge gibst du einfach im Gespräch. Wischen stoppt einen laufenden.") }
            if !m.rooms.isEmpty {
                Section {
                    ForEach(m.rooms) { r in
                        HStack {
                            Text("\(RoomLive.label([r.name])) bis \(r.until, style: .time)").lineLimit(1)
                            Spacer()
                            Button("+30 Min.") { Task { await m.extend(r) } }.buttonStyle(.bordered)
                        }
                    }
                } header: { Text("Raum-Modus") } footer: { Text("Höchstens vier Stunden ab jetzt.") }
            }
        }
        .navigationTitle("Von selbst")
        .refreshable { await m.load() }
        .task { await m.load() }
    }

    static func state(_ s: String) -> String {
        switch s {
        case "queued": return String(localized: "wartet")
        case "running": return String(localized: "läuft")
        case "done": return String(localized: "fertig")
        case "cancelled": return String(localized: "gestoppt")
        default: return String(localized: "Fehler")
        }
    }
}

struct JobView: View {
    let job: Job
    @State private var report = ""
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(verbatim: job.task).font(.headline)
                if !job.error.isEmpty { Text(verbatim: job.error).foregroundStyle(.red) }
                // the job's report: what the language model wrote from outside sources, shown as plain text
                Text(verbatim: report.isEmpty ? job.summary : report).textSelection(.enabled)
                if let e = error { Text(verbatim: e).foregroundStyle(.red) }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .navigationTitle("Auftrag")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            do {
                let d = try await SparkAPI.current?.object("GET", "api/profile/agent/jobs/\(job.id)")
                report = String((d?["report"] as? String ?? "").prefix(200_000))
            } catch { self.error = error.localizedDescription }
        }
    }
}

// MARK: - Sicherheit

@MainActor
final class SecurityModel: ObservableObject {
    @Published var devices: [(id: String, name: String, kind: String, last: Date?)] = []
    @Published var events: [(event: String, at: Date)] = []
    @Published var mfaOn = false
    @Published var codesLeft = 0
    @Published var recovery: [String] = []
    @Published var note: String?
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/security")
            devices = (d["devices"] as? [[String: Any]] ?? []).prefix(50).compactMap { x in
                guard let id = x["id"] as? String, SparkAPI.devId(id) else { return nil }
                let kind = x["app"] as? Bool == true ? "iphone" : x["watch"] as? Bool == true ? "watch" : x["speaker"] as? Bool == true ? "speaker" : "other"
                let t = ((x["last"] as? [String: Any])?["t"] as? NSNumber)?.doubleValue
                return (id, String((x["name"] as? String ?? "").prefix(40)), kind, t.map { Date(timeIntervalSince1970: $0) })
            }
            events = (d["events"] as? [[String: Any]] ?? []).prefix(8).map {
                ($0["event"] as? String ?? "", Date(timeIntervalSince1970: ($0["t"] as? NSNumber)?.doubleValue ?? 0))
            }
            let m = try await api.object("GET", "api/profile/mfa")
            mfaOn = m["on"] as? Bool ?? false
            codesLeft = (m["codes_left"] as? NSNumber)?.intValue ?? 0
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func remove(_ id: String) async {
        guard SparkAPI.devId(id) else { return }
        do { _ = try await SparkAPI.current?.call("DELETE", "api/profile/devices/\(id)"); await load() }
        catch { self.error = error.localizedDescription }
    }

    func logoutAll() async {
        do {
            _ = try await SparkAPI.current?.call("POST", "api/profile/logout-all")
            note = String(localized: "In allen Browsern abgemeldet. Gekoppelte Geräte bleiben.")
            await load()
        } catch { self.error = error.localizedDescription }
    }

    func mfa(_ step: String, code: String) async {
        do {
            let d = try await SparkAPI.current?.object("POST", "api/profile/mfa/\(step)", body: [:], code: code)
            recovery = (d?["recovery"] as? [String] ?? []).prefix(20).map { String($0.prefix(40)) }
            if step == "disable" { note = String(localized: "Der zweite Anmeldeschritt ist aus.") }
            await load()
        } catch { self.error = error.localizedDescription }
    }

    static func label(_ event: String) -> String {
        switch event {
        case "profile_login": return String(localized: "Anmeldung")
        case "profile_login_failed": return String(localized: "Falsche PIN")
        case "profile_code_failed": return String(localized: "Falscher Code")
        case "profile_logout_all": return String(localized: "Überall abgemeldet")
        case "profile_device_removed": return String(localized: "Gerät entfernt")
        case "profile_mfa_on": return String(localized: "Zweiter Schritt eingeschaltet")
        case "profile_mfa_off": return String(localized: "Zweiter Schritt ausgeschaltet")
        default: return String(localized: "Zweiter Schritt zurückgesetzt")
        }
    }
}

struct SecurityView: View {
    static let setUp = "me=secbox"   // Ich → Sicherheit in the panel
    @StateObject private var m = SecurityModel()
    @State private var ask: CodeRequest?
    @State private var removing: String?
    @State private var confirmAll = false

    var body: some View {
        Form {
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            Section {
                LabeledContent("Zweiter Schritt", value: m.mfaOn ? String(localized: "an") : String(localized: "aus"))
                if m.mfaOn {
                    LabeledContent("Wiederherstellungscodes übrig", value: "\(m.codesLeft)")
                    Button("Neue Wiederherstellungscodes") { ask = CodeRequest { c in await m.mfa("recovery", code: c) } }
                    Button("Zweiten Schritt ausschalten", role: .destructive) { ask = CodeRequest { c in await m.mfa("disable", code: c) } }
                } else if let url = SparkAPI.panelLink(Self.setUp) {
                    Link("Im Panel einrichten", destination: url)
                }
                if !m.recovery.isEmpty {
                    Text(verbatim: m.recovery.joined(separator: "\n")).font(.body.monospaced()).textSelection(.enabled)
                    Text("Jetzt sicher aufheben. Sie werden nicht noch einmal gezeigt.").font(.caption).foregroundStyle(.secondary)
                }
            } header: { Text("Anmeldung") } footer: {
                Text("Einrichten geht nur im Browser mit deiner PIN: so beweist nicht allein dieses iPhone, wer du bist.")
            }
            Section {
                ForEach(m.devices, id: \.id) { d in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: d.name)
                        HStack {
                            Text(verbatim: Self.kind(d.kind))
                            if let last = d.last { Text(last, format: .dateTime.day().month().hour().minute()) }
                        }
                        .font(.caption).foregroundStyle(.secondary)
                    }
                    .swipeActions { Button("Entfernen", role: .destructive) { removing = d.id } }
                }
                Button("Überall abmelden", role: .destructive) { confirmAll = true }
            } header: { Text("Meine Geräte") } footer: {
                Text("Wischen entfernt ein Gerät, sein Schlüssel gilt dann sofort nicht mehr. Überall abmelden beendet die Anmeldung in allen Browsern.")
            }
            Section {
                ForEach(Array(m.events.enumerated()), id: \.offset) { _, e in
                    LabeledContent(SecurityModel.label(e.event)) { Text(e.at, format: .dateTime.day().month().hour().minute()) }
                }
            } header: { Text("Letzte Anmeldungen") }
        }
        .navigationTitle("Sicherheit")
        .refreshable { await m.load() }
        .task { await m.load() }
        .codeAlert($ask)
        .confirmationDialog("Gerät entfernen?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                            titleVisibility: .visible, presenting: removing) { id in
            Button("Entfernen", role: .destructive) { Task { await m.remove(id) } }
        } message: { _ in Text("Ist es dieses iPhone, musst du es danach neu koppeln.") }
        .confirmationDialog("In allen Browsern abmelden?", isPresented: $confirmAll, titleVisibility: .visible) {
            Button("Überall abmelden", role: .destructive) { Task { await m.logoutAll() } }
        }
    }

    static func kind(_ k: String) -> String {
        switch k {
        case "iphone": return String(localized: "iPhone-App")
        case "watch": return String(localized: "Uhr")
        case "speaker": return String(localized: "Lautsprecher")
        default: return String(localized: "Gerät")
        }
    }
}

// MARK: - Konten verbinden

/// Mailboxes, calendars, address books, Home Assistant and Telegram. A password or token goes once to the
/// Spark (which keeps it encrypted and never sends it back); the app does not store it. Adding needs the
/// profile's second step and a fresh code.
@MainActor
final class AccountsModel: ObservableObject {
    @Published var mail: [(id: String, name: String, user: String)] = []
    @Published var calendars: [(id: String, name: String, user: String)] = []
    @Published var books: [(id: String, name: String, user: String)] = []
    @Published var ha = ""
    @Published var telegram: String?
    @Published var telegramOn = false
    @Published var link: URL?
    @Published var note: String?
    @Published var error: String?

    private static func rows(_ d: [String: Any]?, _ key: String) -> [(id: String, name: String, user: String)] {
        ((d?[key] as? [[String: Any]]) ?? []).prefix(20).compactMap { x in
            guard let id = x["id"] as? String, SparkAPI.accId(id) else { return nil }
            return (id, String((x["name"] as? String ?? "").prefix(60)), String((x["user"] as? String ?? "").prefix(200)))
        }
    }

    func load() async {
        guard let api = SparkAPI.current else { return }
        mail = Self.rows(try? await api.object("GET", "api/profile/mail"), "accounts")
        calendars = Self.rows(try? await api.object("GET", "api/profile/calendar"), "calendars")
        books = Self.rows(try? await api.object("GET", "api/profile/contacts"), "accounts")
        ha = (try? await api.object("GET", "api/profile/homeassistant"))?["url"] as? String ?? ""
        if let t = try? await api.object("GET", "api/profile/telegram") {
            telegramOn = t["enabled"] as? Bool ?? false
            telegram = (t["linked"] as? [String: Any])?["name"] as? String
        }
    }

    func add(_ path: String, _ body: [String: Any], code: String) async -> Bool {
        do {
            let d = try await SparkAPI.current?.object(path == "api/profile/homeassistant" ? "PUT" : "POST", path, body: body, code: code, timeout: 90)
            note = (d?["check"] as? NSNumber).map { String(localized: "Verbunden, \($0.intValue) gefunden.") } ?? String(localized: "Verbunden.")
            error = nil
            await load()
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func remove(_ path: String) async {
        do { _ = try await SparkAPI.current?.call("DELETE", path); await load() }
        catch { self.error = error.localizedDescription }
    }

    func linkTelegram(code: String) async {
        do {
            let d = try await SparkAPI.current?.object("POST", "api/profile/telegram/link", body: [:], code: code)
            link = (d?["url"] as? String).flatMap { $0.hasPrefix("https://t.me/") ? URL(string: $0) : nil }
            note = String(localized: "Link gilt \((d?["minutes"] as? NSNumber)?.intValue ?? 10) Minuten.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct AccountsView: View {
    @StateObject private var m = AccountsModel()
    @State private var form: String?

    var body: some View {
        Form {
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            list("E-Mail", m.mail, "mail", "api/profile/mail")
            list("Kalender", m.calendars, "calendar", "api/profile/calendar")
            list("Kontakte", m.books, "contacts", "api/profile/contacts")
            Section {
                if m.ha.isEmpty {
                    Button("Verbinden") { form = "ha" }
                } else {
                    LabeledContent("Adresse", value: m.ha)
                    Button("Neu verbinden") { form = "ha" }
                    Button("Trennen", role: .destructive) { Task { await m.remove("api/profile/homeassistant") } }
                }
            } header: { Text("Smart Home") }
            if m.telegramOn {
                Section {
                    if let name = m.telegram {
                        LabeledContent("Verbunden mit", value: name)
                        Button("Trennen", role: .destructive) { Task { await m.remove("api/profile/telegram") } }
                    } else {
                        TelegramLinkButton(m: m)
                        if let link = m.link { Link("In Telegram öffnen", destination: link) }
                    }
                } header: { Text("Telegram") }
            }
        }
        .navigationTitle("Konten verbinden")
        .refreshable { await m.load() }
        .task { await m.load() }
        .sheet(item: Binding(get: { form.map { AccountForm.Kind(id: $0) } }, set: { form = $0?.id })) { k in
            NavigationStack { AccountForm(kind: k.id, m: m) }
        }
    }

    @ViewBuilder private func list(_ title: LocalizedStringKey, _ rows: [(id: String, name: String, user: String)],
                                   _ kind: String, _ path: String) -> some View {
        Section {
            ForEach(rows, id: \.id) { r in
                VStack(alignment: .leading) {
                    Text(verbatim: r.name)
                    if !r.user.isEmpty { Text(verbatim: r.user).font(.caption).foregroundStyle(.secondary) }
                }
                .swipeActions { Button("Entfernen", role: .destructive) { Task { await m.remove("\(path)/\(r.id)") } } }
            }
            Button("Hinzufügen") { form = kind }
        } header: { Text(title) }
    }
}

struct TelegramLinkButton: View {
    @ObservedObject var m: AccountsModel
    @State private var ask: CodeRequest?

    var body: some View {
        Button("Verbindungs-Link holen") { ask = CodeRequest { c in await m.linkTelegram(code: c) } }
            .codeAlert($ask)
    }
}

/// The form for one account. The password lives only in this form until it is sent.
struct AccountForm: View {
    struct Kind: Identifiable { let id: String }
    let kind: String
    @ObservedObject var m: AccountsModel
    @Environment(\.dismiss) private var dismiss
    @State private var provider = "icloud"
    @State private var name = ""
    @State private var host = ""
    @State private var url = ""
    @State private var user = ""
    @State private var secret = ""
    @State private var ask: CodeRequest?

    var body: some View {
        Form {
            switch kind {
            case "mail":
                Picker("Anbieter", selection: $provider) {
                    Text(verbatim: "iCloud").tag("icloud")
                    Text(verbatim: "Gmail").tag("gmail")
                    Text(verbatim: "GMX").tag("gmx")
                    Text(verbatim: "web.de").tag("webde")
                    Text("Anderer").tag("")
                }
                if provider.isEmpty { TextField("IMAP-Server, z. B. imap.example.de", text: $host).textInputAutocapitalization(.never).autocorrectionDisabled() }
                TextField("Benutzer (E-Mail-Adresse)", text: $user).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.emailAddress)
                SecureField("App-Passwort", text: $secret)
            case "ha":
                TextField("Adresse, z. B. http://homeassistant.local:8123", text: $url).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                SecureField("Langlebiger Zugriffstoken", text: $secret)
            default:
                TextField("Name", text: $name)
                TextField(kind == "calendar" ? String(localized: "CalDAV-Adresse (https://…)") : String(localized: "CardDAV-Adresse (https://…)"), text: $url)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                TextField("Benutzer", text: $user).textInputAutocapitalization(.never).autocorrectionDisabled()
                SecureField("App-Passwort", text: $secret)
            }
            Section {
                Button("Verbinden") { ask = CodeRequest { c in await send(code: c) } }
                    .disabled(secret.isEmpty || (kind != "mail" && url.isEmpty) || (kind == "mail" && user.isEmpty))
            } footer: {
                Text("Der Spark prüft die Verbindung, speichert das Passwort verschlüsselt und gibt es nie wieder heraus. Das iPhone behält es nicht. Bestätigt wird mit dem Code aus der Authenticator-App.")
            }
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
        }
        .navigationTitle(Self.title(kind))
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { secret = ""; dismiss() } } }
        .codeAlert($ask)
        .onDisappear { secret = "" }
    }

    private func send(code: String) async {
        var body: [String: Any]
        let path: String
        switch kind {
        case "mail":
            body = ["kind": provider, "user": user, "password": secret]
            if provider.isEmpty { body["host"] = host }
            path = "api/profile/mail"
        case "ha":
            body = ["url": url, "token": secret]
            path = "api/profile/homeassistant"
        case "calendar":
            body = ["name": name, "url": url, "user": user, "password": secret, "tz": TimeZone.current.identifier]
            path = "api/profile/calendar"
        default:
            body = ["name": name, "url": url, "user": user, "password": secret]
            path = "api/profile/contacts"
        }
        if await m.add(path, body, code: code) {
            secret = ""
            dismiss()
        }
    }

    static func title(_ kind: String) -> String {
        switch kind {
        case "mail": return String(localized: "E-Mail")
        case "ha": return String(localized: "Smart Home")
        case "calendar": return String(localized: "Kalender")
        default: return String(localized: "Kontakte")
        }
    }
}
