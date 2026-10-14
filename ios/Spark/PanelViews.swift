import SafariServices
import SwiftUI

/// "Im Panel öffnen": every page of Ich the app does not show itself, opened inside the app at the right place
/// (the profile signs in there once, like in the browser). The list of pages comes from the Spark
/// (/api/features "pages", features.ME_PAGES), never from a list here: a new page shows up without an app update
/// (Richtlinie, App-Gleichstand, Dominik 2026-10-14). The app takes over more of them bit by bit.
struct PanelBridgeView: View {
    let admin: Bool
    /// the Ich pages this profile can use now, in the panel's order: (place "me=<page>", name)
    @State private var pages: [(String, String)] = []
    @State private var loaded = false
    @State private var open: PanelPlace?

    static let spark: [(LocalizedStringKey, String)] = [
        (LocalizedStringKey("Monitoring"), "go=mon"), (LocalizedStringKey("Prüfen"), "go=test"), (LocalizedStringKey("Logs"), "go=logs"), (LocalizedStringKey("Einstellungen"), "go=cfg"),
        (LocalizedStringKey("Funktionen"), "cfg=feat"), (LocalizedStringKey("Update und Sicherung"), "cfg=upd"), (LocalizedStringKey("Personen und Geräte"), "go=prof"),
        (LocalizedStringKey("Anleitungen"), "go=int"),
    ]

    var body: some View {
        List {
            Section {
                if !loaded { ProgressView() }
                ForEach(pages, id: \.0) { p in row(Text(verbatim: p.1), p.0) }
            } header: { Text("Ich") } footer: {
                Text("Öffnet das Panel hier in der App an dieser Stelle. Beim ersten Mal meldest du dich an wie im Browser.")
            }
            if admin {
                Section("Spark verwalten") {
                    ForEach(Self.spark, id: \.1) { row(Text($0.0), $0.1) }
                }
            }
        }
        .navigationTitle("Im Panel öffnen")
        .task { await load() }
        .sheet(item: $open) { p in PanelPage(url: p.url).ignoresSafeArea() }
    }

    @ViewBuilder private func row(_ title: Text, _ place: String) -> some View {
        if let url = SparkAPI.panelLink(place) {
            Button { open = PanelPlace(url: url) } label: {
                LabeledContent {
                    Image(systemName: "chevron.right").foregroundStyle(.secondary)
                } label: { title }
            }
            .foregroundStyle(.primary)
        }
    }

    private func load() async {
        defer { loaded = true }
        guard let api = SparkAPI.current, let d = try? await api.object("GET", "api/features"),
              let list = d["pages"] as? [[String: Any]] else { return }
        pages = list.prefix(60).compactMap { p in
            guard let id = p["id"] as? String, id.range(of: #"^[a-z]{2,12}$"#, options: .regularExpression) != nil,
                  let name = FeaturesView.pick(p["name"]) else { return nil }
            return ("me=" + id, name)
        }
    }
}

/// A page of the panel to open inside the app.
struct PanelPlace: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

/// The panel inside the app (SFSafariViewController): Safari's protections, the profile's own sign-in, no
/// access for the app to what is on the page.
struct PanelPage: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let c = SFSafariViewController(url: url)
        c.dismissButtonStyle = .done
        return c
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
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
                Section { Text(SparkAPI.way(e)).foregroundStyle(.secondary) }
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
