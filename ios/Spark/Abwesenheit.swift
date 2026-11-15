import SwiftUI

// MARK: - Abwesenheit

/// Abwesenheit (abwesenheit.py, Nextcloud-Ideen 1): from–until, a text for replies, a stand-in and two switches. The
/// Spark uses it by fixed rules (calendar, chats, calls, the mail reply); the app only shows, saves and deletes it.
@MainActor
final class AbwesenheitModel: ObservableObject {
    @Published var von = Date()
    @Published var bis = Date().addingTimeInterval(7 * 86400)
    @Published var text = ""
    @Published var vertretung = ""
    @Published var mail = false
    @Published var kalender = true
    @Published var has = false
    @Published var active = false
    @Published var maxText = 2000
    @Published var error: String?
    @Published var note: String?

    private static let fmt: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    /// A day "YYYY-MM-DD" of the Spark as a date at 00:00 here.
    static func day(_ s: String) -> Date? {
        s.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) == nil ? nil : fmt.date(from: s)
    }

    func load() async {
        do {
            let d = try await SparkAPI.current?.object("GET", "api/profile/abwesenheit") ?? [:]
            show(d)
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func show(_ d: [String: Any]) {
        maxText = (d["max_text"] as? NSNumber)?.intValue ?? maxText
        guard let e = d["eintrag"] as? [String: Any], let v = Self.day(e["von"] as? String ?? ""),
              let b = Self.day(e["bis"] as? String ?? "") else {
            has = false
            active = false
            return
        }
        has = true
        von = v
        bis = b
        text = String((e["text"] as? String ?? "").prefix(maxText))
        vertretung = String((e["vertretung"] as? String ?? "").prefix(60))
        mail = e["mail"] as? Bool ?? false
        kalender = e["kalender"] as? Bool ?? true
        active = ((e["start"] as? NSNumber)?.doubleValue ?? .infinity) <= Date().timeIntervalSince1970
    }

    func save() async {
        let body: [String: Any] = ["von": Self.fmt.string(from: von), "bis": Self.fmt.string(from: bis),
                                   "text": String(text.prefix(maxText)), "vertretung": String(vertretung.prefix(60)),
                                   "mail": mail, "kalender": kalender, "tz": TimeZone.current.identifier]
        do {
            let d = try await SparkAPI.current?.object("PUT", "api/profile/abwesenheit", body: body) ?? [:]
            show(d)
            note = String(localized: "Gespeichert.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func end() async {
        do {
            let d = try await SparkAPI.current?.object("DELETE", "api/profile/abwesenheit") ?? [:]
            show(d)
            note = String(localized: "Abwesenheit beendet.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct AbwesenheitView: View {
    @StateObject private var m = AbwesenheitModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            Section {
                DatePicker("Von", selection: $m.von, displayedComponents: .date)
                DatePicker("Bis", selection: $m.bis, in: m.von..., displayedComponents: .date)
            } header: {
                Text(m.has ? (m.active ? LocalizedStringKey("Aktiv") : LocalizedStringKey("Eingetragen")) : LocalizedStringKey("Abwesenheit"))
            } footer: {
                Text("Während du weg bist: ein ganztägiger Eintrag im Kalender, „abwesend bis …“ neben deinem Namen in den Chats, Anrufe klingeln nicht, und wer dich anrufen will, hört, bis wann du weg bist und wer dich vertritt.")
            }
            Section("Text für Antworten") {
                TextEditor(text: $m.text).frame(minHeight: 90)
            }
            Section {
                TextField("Vertretung", text: $m.vertretung).textInputAutocapitalization(.words)
                Toggle("Mail-Antwort (einmal pro Absender, nie an Newsletter)", isOn: $m.mail)
                Toggle("Im Kalender zeigen", isOn: $m.kalender)
            }
            Section {
                Button("Speichern") { Task { await m.save() } }
                if m.has {
                    Button("Abwesenheit beenden", role: .destructive) { Task { await m.end() } }
                }
            }
        }
        .navigationTitle("Abwesenheit")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fertig") { dismiss() } } }
        .task { await m.load() }
    }
}
