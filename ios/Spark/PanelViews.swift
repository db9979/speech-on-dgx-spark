import SafariServices
import SwiftUI

/// "Im Panel öffnen": every page of Ich the app does not show itself, opened inside the app at the right place
/// (the profile signs in there once, like in the browser). The list of pages comes from the Spark
/// (/api/features "pages", features.ME_PAGES), never from a list here: a new page shows up without an app update
/// (Richtlinie, App-Gleichstand, Dominik 2026-10-14). The app takes over more of them bit by bit: a page with "app"
/// (features.APP_NATIVE) leads to the app's own view (NativePage), a long press still opens it in the panel.
struct PanelBridgeView: View {
    let admin: Bool
    @EnvironmentObject var talk: Conversation
    /// the Ich pages this profile can use now, in the panel's order: (place "me=<page>", name, the app's own view)
    @State private var pages: [(String, String, NativePage?)] = []
    @State private var loaded = false
    @State private var open: PanelPlace?

    static let spark: [(LocalizedStringKey, String)] = [
        (LocalizedStringKey("Überblick"), "go=mon"), (LocalizedStringKey("Prüfen"), "go=test"), (LocalizedStringKey("Werkstatt"), "go=werk"), (LocalizedStringKey("Logs"), "go=logs"), (LocalizedStringKey("Einstellungen"), "go=cfg"),
        (LocalizedStringKey("Funktionen"), "cfg=feat"), (LocalizedStringKey("Update und Sicherung"), "cfg=upd"), (LocalizedStringKey("Personen und Geräte"), "go=prof"),
        (LocalizedStringKey("Fernzugang"), "go=fern"),
    ]

    var body: some View {
        List {
            Section {
                if !loaded { LadeZeilen(rows: 4) }
                ForEach(pages, id: \.0) { p in
                    if let n = p.2, n.open(talk.allowed) {
                        NavigationLink { n.page } label: { Text(verbatim: p.1) }
                            .contextMenu { panelButton(p.0) }
                    } else {
                        row(Text(verbatim: p.1), p.0)
                    }
                }
            } header: { Text("Ich") } footer: {
                Text("Was die App selbst kann, öffnet sie direkt. Alles andere zeigt das Panel hier in der App; beim ersten Mal meldest du dich an wie im Browser. Lange drücken öffnet auch eine App-Seite im Panel.")
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

    @ViewBuilder private func panelButton(_ place: String) -> some View {
        if let url = SparkAPI.panelLink(place) {
            Button { open = PanelPlace(url: url) } label: { Label("Im Panel öffnen", systemImage: "safari") }
        }
    }

    private func load() async {
        defer { loaded = true }
        if pages.isEmpty, let k = Merken.object("funktionen") {   // the last state first (Merken.swift)
            pages = Self.pages(k.d)
            loaded = true
        }
        guard let api = SparkAPI.current, let d = try? await api.object("GET", "api/features") else { return }
        Merken.keepObject("funktionen", d)
        pages = Self.pages(d)
    }

    private static func pages(_ d: [String: Any]) -> [(String, String, NativePage?)] {
        guard let list = d["pages"] as? [[String: Any]] else { return [] }
        return list.prefix(60).compactMap { p in
            guard let id = p["id"] as? String, id.range(of: #"^[a-z]{2,12}$"#, options: .regularExpression) != nil,
                  let name = FeaturesView.pick(p["name"]) else { return nil }
            return ("me=" + id, name, (p["app"] as? String).flatMap(NativePage.init(rawValue:)))
        }
    }
}

/// The app's own view of an Ich page or a page of its own (features.APP_NATIVE, the same words): a word this app
/// does not know yet (an older app) opens the panel as before. `area` is the app's right for it (iphone.AREAS,
/// iphone.THINGS); without it the panel opens, which says why.
enum NativePage: String {
    case kalender, post, listen, offen, kontakte, wissensbuch, finden, mappen
    case zustand, gedaechtnis, dokumente, bilder, musik, ichweiss, vonselbst, sicherheit, stimme, profil, lautsprecher

    var area: String? {
        switch self {
        case .kalender: return "calendar"
        case .post: return "mail"
        case .listen: return "tasks"
        case .offen: return "vorgaenge"
        case .kontakte: return "contacts"
        case .wissensbuch: return "wissensbuch"
        case .finden: return "fund"
        case .mappen: return "mappen"
        case .gedaechtnis: return "memory"
        case .dokumente: return "documents"
        case .bilder: return "bilder"
        case .musik: return "musik"
        case .ichweiss: return "ichweiss"
        case .vonselbst: return "app_auto"
        case .sicherheit: return "app_security"
        case .stimme: return "app_voice"
        case .lautsprecher: return "esp32"
        case .zustand, .profil: return nil   // the Spark lists the page only when the profile may use it
        }
    }

    func open(_ a: Allowed) -> Bool { area.map { a.areas.contains($0) } ?? true }

    @MainActor @ViewBuilder var page: some View {
        switch self {
        case .kalender: KalenderView()
        case .post: PostView()
        case .listen: ListenView()
        case .offen: OffenView()
        case .kontakte: KontakteView()
        case .wissensbuch: WissensbuchView()
        case .finden: FindenView()
        case .mappen: MappenView()
        case .zustand: MyStatusView()
        case .gedaechtnis: MemoryView()
        case .dokumente: DocumentsView()
        case .bilder: PicturesView()
        case .musik: SongsView()
        case .ichweiss: IchWeissView()
        case .vonselbst: AutoView()
        case .sicherheit: SecurityView()
        case .stimme: VoiceView()
        case .profil: ProfileView()
        case .lautsprecher: LautsprecherView()
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

/// "Mein Alltag": the next appointments and the Spark's own reminders (the memory is under Meine Sachen).
@MainActor
final class MineModel: ObservableObject {
    @Published var events: [String] = []
    @Published var calendarNote: String?
    @Published var reminders: [Reminder] = []
    @Published var loading = true
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
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

    func done(_ r: Reminder) async {
        do { try await SparkAPI.current?.deleteReminder(r.id); reminders.removeAll { $0.id == r.id } }
        catch { self.error = error.localizedDescription }
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
        }
        .navigationTitle("Mein Alltag")
        .refreshable { await m.load() }
        .task { await m.load() }
    }
}
