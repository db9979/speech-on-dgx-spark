import SwiftUI

// ---------------------------------------------------------------- Probleme melden (thread „Issues melden“, meldung.py)
/// A problem report from the app: describe it, the Spark makes an anonymized draft (with the app's sound log if
/// wanted), the app shows exactly what would go out, lines can be unticked, and only a tap sends it to GitHub, opens
/// it in the browser or keeps it on the Spark. The Spark checks everything again (signature, leak check, limits);
/// the app only shows its answers. Off in the panel: the Spark answers 404/403 and the page says so.
struct ReportSection: View {
    var body: some View {
        Section {
            NavigationLink("Problem melden") { ReportView() }
        } footer: {
            Text("Geht anonymisiert als Meldung an GitHub. Du siehst vorher genau, was rausgeht.")
        }
    }
}

struct ReportView: View {
    struct Line: Identifiable { let id: Int; let part: String; let text: String }
    struct Area: Identifiable { let id: String; let name: String }

    @Environment(\.openURL) private var openURL
    @State private var text = ""
    @State private var area = "app"
    @State private var areas: [Area] = []
    @State private var withLog = true
    @State private var draft: String?
    @State private var lines: [Line] = []
    @State private var skip = Set<Int>()
    @State private var title = ""
    @State private var preview = ""
    @State private var sig = ""
    @State private var leaks: [String] = []
    @State private var token = false
    @State private var busy = false
    @State private var note: String?

    var body: some View {
        Form {
            if let draft {
                Section("Vorschau") {
                    Text(verbatim: title).font(.headline)
                    Text(verbatim: preview).font(.caption.monospaced()).textSelection(.enabled)
                    if !leaks.isEmpty {
                        Text(verbatim: String(localized: "Die Prüfung hat noch etwas gefunden: ") + leaks.joined(separator: ", "))
                            .foregroundStyle(.red)
                    }
                }
                if !lines.isEmpty {
                    Section {
                        ForEach(lines) { l in
                            Toggle(isOn: Binding(get: { !skip.contains(l.id) }, set: { on in
                                if on { skip.remove(l.id) } else { skip.insert(l.id) }
                                Task { await refresh(draft) }
                            })) {
                                Text(verbatim: l.text).font(.caption.monospaced()).lineLimit(3)
                            }
                        }
                    } header: { Text("Zeilen") } footer: { Text("Abgewählte Zeilen gehen nicht mit.") }
                }
                Section {
                    Button("An GitHub senden") { send(["sig": sig]) }.disabled(busy || sig.isEmpty || !token)
                    Button("Im Browser öffnen") { send(["sig": sig, "browser": true]) }.disabled(busy || sig.isEmpty)
                    Button("Nur lokal behalten") { send(["local": true]) }.disabled(busy)
                } footer: {
                    Text(token ? String(localized: "Erst dein Tipp schickt es los.")
                         : String(localized: "Der Spark hat noch keinen Token: „Im Browser öffnen“ füllt die Meldung auf GitHub aus."))
                }
            } else {
                Section {
                    TextField("Was ist passiert?", text: $text, axis: .vertical).lineLimit(3...8)
                    if !areas.isEmpty {
                        Picker("Bereich", selection: $area) {
                            ForEach(areas) { a in Text(verbatim: a.name).tag(a.id) }
                        }
                    }
                    Toggle("Ton-Protokoll der App anhängen", isOn: $withLog)
                } footer: {
                    Text("Der Spark ersetzt Namen, Mail-Adressen, Adressen und Inhalte durch Platzhalter. Dazu kommen deine letzten Anfragen (nur Wege, Werkzeuge, Zeiten) und der Systemzustand.")
                }
                Section {
                    Button("Entwurf anlegen und ansehen") { make() }
                        .disabled(busy || text.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
                }
            }
            if let note { Section { Text(SparkAPI.way(note)) } }
        }
        .navigationTitle("Problem melden")
        .task { await load() }
    }

    private var api: SparkAPI? { SparkAPI.current }

    private func load() async {
        guard let api else { note = String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."); return }
        do {
            let (data, response) = try await URLSession.shared.data(for: api.request("api/report"))
            if let http = response as? HTTPURLResponse, http.statusCode == 404 || http.statusCode == 403 {
                note = String(localized: "Probleme melden ist für dich aus. Der Admin hat es noch nicht freigegeben (Funktionen → Probleme melden).")
                return
            }
            try SparkAPI.check(data, response)
            let d = SparkAPI.object(data)
            token = d["token"] as? Bool == true
            areas = (d["areas"] as? [[String: Any]] ?? []).compactMap { a in
                guard let k = a["key"] as? String, let n = a["name"] as? [String], let de = n.first else { return nil }
                return Area(id: k, name: de)
            }
        } catch {
            note = error.localizedDescription
        }
    }

    private func make() {
        guard let api else { return }
        busy = true
        note = String(localized: "Lege an und anonymisiere …")
        Task {
            do {
                var body: [String: Any] = ["text": text, "area": area, "minutes": 30]
                if withLog { body["applog"] = AudioEngine.diary.suffix(150).joined(separator: "\n") }
                let d = try await api.post("api/report/draft", body)
                show(d)
                note = nil
            } catch {
                note = error.localizedDescription
            }
            busy = false
        }
    }

    private func show(_ d: [String: Any]) {
        draft = d["id"] as? String
        lines = (d["lines"] as? [[String: Any]] ?? []).compactMap { l in
            guard let n = (l["n"] as? NSNumber)?.intValue else { return nil }
            return Line(id: n, part: l["part"] as? String ?? "", text: l["line"] as? String ?? "")
        }
        skip = []
        paint(d["preview"] as? [String: Any] ?? [:])
    }

    private func paint(_ p: [String: Any]) {
        title = p["title"] as? String ?? ""
        preview = p["body"] as? String ?? ""
        sig = p["sig"] as? String ?? ""
        leaks = p["leaks"] as? [String] ?? []
    }

    private func refresh(_ id: String) async {
        guard let api else { return }
        do { paint(try await api.post("api/report/preview", ["id": id, "skip": Array(skip).sorted()])) } catch { note = error.localizedDescription }
    }

    private func send(_ extra: [String: Any]) {
        guard let api, let draft else { return }
        busy = true
        Task {
            do {
                var body = extra
                body["id"] = draft
                body["skip"] = Array(skip).sorted()
                let d = try await api.post("api/report/send", body)
                if let s = d["url"] as? String, let url = URL(string: s), url.scheme == "https", url.host == "github.com" {
                    openURL(url)
                    note = String(localized: "GitHub ist offen. Dort auf „Create“ tippen; der Entwurf bleibt auf dem Spark.")
                } else if let issue = d["issue"] as? [String: Any], let n = (issue["number"] as? NSNumber)?.intValue {
                    note = String(localized: "Gesendet als Meldung Nummer \(n).")
                    reset()
                } else {
                    note = String(localized: "Auf dem Spark abgelegt.")
                    reset()
                }
            } catch {
                note = error.localizedDescription
            }
            busy = false
        }
    }

    private func reset() {
        draft = nil
        text = ""
        lines = []
        skip = []
    }
}
