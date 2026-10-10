import SwiftUI

/// "Im Panel öffnen": every part of the panel the app does not show itself, opened in Safari at the right
/// place (the profile signs in there as usual). The app takes over more of them bit by bit.
struct PanelBridgeView: View {
    let admin: Bool

    static let mine: [(LocalizedStringKey, String)] = [
        (LocalizedStringKey("Gespräch"), "me=setbox"), (LocalizedStringKey("Gedächtnis"), "me=factbox"), (LocalizedStringKey("Dokumente"), "me=docbox"), (LocalizedStringKey("Protokoll"), "me=logbox"),
        (LocalizedStringKey("Kalender"), "me=calbox"), (LocalizedStringKey("Aufgaben"), "me=taskbox"), (LocalizedStringKey("Aufträge"), "me=agentbox"), (LocalizedStringKey("Nachrichten"), "me=msgbox"),
        (LocalizedStringKey("Wetter"), "me=wxbox"), (LocalizedStringKey("Von selbst"), "me=probox"), (LocalizedStringKey("Mitteilungen"), "me=notebox"), (LocalizedStringKey("E-Mail"), "me=mailbox"),
        (LocalizedStringKey("Pakete"), "me=parbox"), (LocalizedStringKey("Kontakte"), "me=conbox"), (LocalizedStringKey("Smart Home"), "me=habox"), (LocalizedStringKey("Raum-Modus"), "me=roombox"),
        (LocalizedStringKey("Lautsprecher"), "me=espbox"), (LocalizedStringKey("Bus und Bahn"), "me=trbox"), (LocalizedStringKey("Telegram"), "me=tgbox"), (LocalizedStringKey("iPhone-App"), "me=appbox"),
        (LocalizedStringKey("Pebble-Uhr"), "me=pebbox"), (LocalizedStringKey("Sicherheit"), "me=secbox"), (LocalizedStringKey("Sprechererkennung"), "me=voicebox"),
    ]
    static let spark: [(LocalizedStringKey, String)] = [
        (LocalizedStringKey("Monitoring"), "go=mon"), (LocalizedStringKey("Prüfen"), "go=test"), (LocalizedStringKey("Logs"), "go=logs"), (LocalizedStringKey("Einstellungen"), "go=cfg"),
        (LocalizedStringKey("Funktionen"), "cfg=feat"), (LocalizedStringKey("Update und Sicherung"), "cfg=upd"), (LocalizedStringKey("Profile und Geräte"), "go=prof"),
        (LocalizedStringKey("Einbinden"), "go=int"),
    ]

    var body: some View {
        List {
            Section {
                ForEach(Self.mine, id: \.1) { row($0.0, $0.1) }
            } header: { Text("Ich") } footer: {
                Text("Öffnet das Panel in Safari an dieser Stelle. Dort meldest du dich an wie gewohnt.")
            }
            if admin {
                Section("Spark verwalten") {
                    ForEach(Self.spark, id: \.1) { row($0.0, $0.1) }
                }
            }
        }
        .navigationTitle("Im Panel öffnen")
    }

    @ViewBuilder private func row(_ title: LocalizedStringKey, _ place: String) -> some View {
        if let url = SparkAPI.panelLink(place) {
            Link(destination: url) {
                LabeledContent(title) { Image(systemName: "arrow.up.forward.app").foregroundStyle(.secondary) }
            }
            .foregroundStyle(.primary)
        }
    }
}

/// "Mein Alltag": what the assistant remembers, the next appointments and the Spark's own reminders.
@MainActor
final class MineModel: ObservableObject {
    @Published var facts: [Fact] = []
    @Published var tidy: MemoryTidy?
    @Published var events: [String] = []
    @Published var calendarNote: String?
    @Published var reminders: [Reminder] = []
    @Published var loading = true
    @Published var asking = false
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            (facts, tidy) = try await api.memory()
            reminders = try await api.reminders().sorted { $0.due < $1.due }
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
        do {
            let r = try await api.nextEvents()
            events = r.events
            calendarNote = r.errors.isEmpty ? (r.events.isEmpty ? String(localized: "Keine Termine in den nächsten 14 Tagen.") : nil)
                                            : r.errors.joined(separator: "\n")
        } catch {
            calendarNote = String(localized: "Noch kein Kalender verbunden.")
        }
    }

    func forget(_ f: Fact) async {
        do { try await SparkAPI.current?.forget(f.id); facts.removeAll { $0.id == f.id } }
        catch { self.error = error.localizedDescription }
    }

    func done(_ r: Reminder) async {
        do { try await SparkAPI.current?.deleteReminder(r.id); reminders.removeAll { $0.id == r.id } }
        catch { self.error = error.localizedDescription }
    }

    func tidyStep(_ step: String) async {
        guard let api = SparkAPI.current else { return }
        asking = true
        defer { asking = false }
        do {
            tidy = try await api.tidyMemory(step)
            if step == "check" && tidy == nil { error = String(localized: "Nichts aufzuräumen.") }
            if step == "accept" { (facts, tidy) = try await api.memory() }
        } catch { self.error = error.localizedDescription }
    }
}

struct MineView: View {
    @StateObject private var m = MineModel()

    var body: some View {
        List {
            if let e = m.error {
                Section { Text(verbatim: e).foregroundStyle(.secondary) }
            }
            Section {
                if m.loading { ProgressView() }
                ForEach(m.events, id: \.self) { Text(verbatim: $0) }
                if let note = m.calendarNote { Text(verbatim: note).foregroundStyle(.secondary) }
            } header: { Text("Die nächsten Termine") }
            Section {
                if m.reminders.isEmpty && !m.loading { Text("Noch keine Einträge.").foregroundStyle(.secondary) }
                ForEach(m.reminders, id: \.id) { r in
                    VStack(alignment: .leading) {
                        Text(verbatim: r.text)
                        Text(r.due, format: .dateTime.weekday().day().month().hour().minute()).font(.caption).foregroundStyle(.secondary)
                    }
                    .swipeActions { Button(role: .destructive) { Task { await m.done(r) } } label: { Label("Löschen", systemImage: "trash") } }
                }
            } header: { Text("Erinnerungen") }
            memory
        }
        .navigationTitle("Mein Alltag")
        .refreshable { await m.load() }
        .task { await m.load() }
    }

    private var memory: some View {
        Section {
            if m.facts.isEmpty && !m.loading { Text("Noch nichts gemerkt.").foregroundStyle(.secondary) }
            ForEach(m.facts) { f in
                VStack(alignment: .leading, spacing: 2) {
                    // what the assistant noted: plain text, nothing in it is a link or a command
                    Text(verbatim: f.text)
                    if f.learned { Text("aus einem Gespräch gelernt").font(.caption).foregroundStyle(.secondary) }
                }
                .swipeActions { Button(role: .destructive) { Task { await m.forget(f) } } label: { Label("Löschen", systemImage: "trash") } }
            }
            if let t = m.tidy {
                ForEach(Array(t.merge.enumerated()), id: \.offset) { _, x in
                    VStack(alignment: .leading) {
                        Text("Zusammenfassen:").font(.caption.bold())
                        ForEach(x.old, id: \.self) { Text(verbatim: "– " + $0).font(.caption).foregroundStyle(.secondary) }
                        Text(verbatim: "→ " + x.text)
                    }
                }
                ForEach(Array(t.drop.enumerated()), id: \.offset) { _, x in
                    VStack(alignment: .leading) {
                        Text("Weglassen:").font(.caption.bold())
                        Text(verbatim: x.old).strikethrough()
                        if !x.why.isEmpty { Text(verbatim: x.why).font(.caption).foregroundStyle(.secondary) }
                    }
                }
                HStack {
                    Button("Übernehmen") { Task { await m.tidyStep("accept") } }.buttonStyle(.borderedProminent)
                    Button("Verwerfen") { Task { await m.tidyStep("reject") } }.buttonStyle(.bordered)
                }
                .disabled(m.asking)
            } else if !m.facts.isEmpty {
                Button {
                    Task { await m.tidyStep("check") }
                } label: {
                    if m.asking { ProgressView() } else { Text("Aufräumen vorschlagen") }
                }
                .disabled(m.asking)
            }
        } header: { Text("Gedächtnis") } footer: {
            Text("Wischen zum Löschen. Aufräumen fasst doppelte Einträge zusammen, erst nach deinem Übernehmen.")
        }
    }
}
