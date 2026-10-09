import SwiftUI

/// Messages between the profiles of this Spark (admin switch "Nachrichten an andere" plus the
/// profile's own switch). What others write is their text: it is only shown here, never acted on.
/// Who may write to me is set in the browser only.
@MainActor
final class MessagesModel: ObservableObject {
    @Published var box = MessageBox()
    @Published var loading = true
    @Published var off = false
    @Published var error: String?
    @Published var notice: String?
    @Published var to = ""
    @Published var text = ""
    @Published var sending = false
    @Published var ready: MessageReady?

    func load() async {
        guard let api = SparkAPI.current else { return }
        ready = try? await api.messagesReady()
        do {
            if let b = try await api.messages() {
                box = b
                off = false
                if to.isEmpty || !(b.to.contains { $0.id == to } || (to == "all" && b.all)) {
                    // the last one written to, else the only one; with many profiles the person picks
                    to = b.recent.first { id in b.to.contains { $0.id == id } } ?? (b.to.count == 1 ? b.to[0].id : "")
                }
                // seen here: read on the Spark too, so the panel and the other devices stop pointing at them
                let unread = b.items.filter { !$0.read }.map(\.id)
                if !unread.isEmpty, (try? await api.markRead(unread)) != nil {
                    for i in box.items.indices { box.items[i].read = true }
                    Conversation.shared.unreadMessages = 0
                }
            } else {
                off = true
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    func send() async {
        guard let api = SparkAPI.current, !sending else { return }
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !to.isEmpty else { return }
        sending = true
        defer { sending = false }
        do {
            try await api.sendMessage(to: to, text: String(t.prefix(box.maxText)))
            text = ""
            error = nil
            notice = String(localized: "Gesendet.")
        } catch {
            notice = nil
            self.error = error.localizedDescription
        }
    }

    func delete(_ ids: [String]) async {
        guard let api = SparkAPI.current else { return }
        do {
            try await api.deleteMessages(ids)
            box.items.removeAll { ids.contains($0.id) }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func toggleFavourite(_ id: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            box.fav = try await api.setFavourite(id, on: !box.fav.contains(id))
        } catch {
            self.error = error.localizedDescription
        }
    }

    var toLabel: String {
        if to == "all" { return String(localized: "Alle") }
        return box.to.first { $0.id == to }?.label ?? String(localized: "Empfänger wählen")
    }

    func answer(_ m: SparkMessage) {
        if box.to.contains(where: { $0.id == m.from }) {
            to = m.from
        } else {
            error = String(localized: "\(m.name) nimmt gerade keine Nachrichten von dir an.")
        }
    }
}

struct MessagesView: View {
    @StateObject private var m = MessagesModel()
    @Environment(\.dismiss) private var dismiss
    @FocusState private var writing: Bool

    var body: some View {
        NavigationStack {
            Form {
                if m.loading {
                    ProgressView()
                } else if m.off {
                    if let r = m.ready { ReadyView(r: r, open: true) } else {
                        Section { Text("Nachrichten sind für dein Profil aus. Einschalten im Panel unter Ich → Nachrichten (der Admin muss sie unter Funktionen erlauben).") }
                    }
                } else {
                    compose
                    inbox
                    if let r = m.ready { ReadyView(r: r, open: false) }
                }
                if let n = m.notice { Section { Text(verbatim: n) } }
                if let e = m.error { Section { Text(verbatim: e).foregroundStyle(.red) } }
            }
            .navigationTitle("Nachrichten")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await m.load() }
            .task { await m.load() }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
    }

    @ViewBuilder private var compose: some View {
        if m.box.to.isEmpty && !m.box.all {
            Section { Text("Gerade nimmt niemand Nachrichten von dir an.").foregroundStyle(.secondary) }
        } else {
            Section {
                NavigationLink {
                    RecipientPicker(m: m)
                } label: {
                    LabeledContent("An") { Text(verbatim: m.toLabel).foregroundStyle(m.to.isEmpty ? .secondary : .primary) }
                }
                TextField("Nachricht", text: $m.text, axis: .vertical)
                    .lineLimit(2...6)
                    .focused($writing)
                    .onChange(of: m.text) { _, t in if t.count > m.box.maxText { m.text = String(t.prefix(m.box.maxText)) } }
                Button {
                    Task { await m.send(); if m.error == nil { writing = false } }
                } label: {
                    if m.sending { ProgressView() } else { Label("Senden", systemImage: "paperplane") }
                }
                .disabled(m.sending || m.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || m.to.isEmpty)
            } header: { Text("Schreiben") } footer: {
                Text("\(m.text.count) / \(m.box.maxText) Zeichen")
            }
        }
    }

    @ViewBuilder private var inbox: some View {
        Section {
            if m.box.items.isEmpty {
                Text("Keine Nachrichten.").foregroundStyle(.secondary)
            }
            ForEach(m.box.items.sorted { $0.date > $1.date }) { msg in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(verbatim: msg.name.isEmpty ? String(localized: "Jemand") : msg.name).bold()
                        Spacer()
                        Text(msg.date, format: .relative(presentation: .named)).font(.caption).foregroundStyle(.secondary)
                    }
                    if msg.voice {
                        Label(msg.secs.map { String(localized: "Sprachnachricht, \($0) s. Anhören im Panel.") }
                              ?? String(localized: "Sprachnachricht. Anhören im Panel."), systemImage: "waveform")
                            .font(.footnote).foregroundStyle(.secondary)
                    } else {
                        // someone else's words: plain text, links and markdown stay text
                        Text(verbatim: msg.text).textSelection(.enabled)
                    }
                }
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) { Task { await m.delete([msg.id]) } } label: { Label("Löschen", systemImage: "trash") }
                }
                .swipeActions(edge: .leading) {
                    Button { m.answer(msg); writing = true } label: { Label("Antworten", systemImage: "arrowshape.turn.up.left") }
                        .tint(.blue)
                }
            }
        } header: { Text("Eingang") } footer: {
            if !m.box.items.isEmpty { Text("Nach links wischen löscht, nach rechts antwortet. Nachrichten bleiben 30 Tage.") }
        }
    }
}

/// The recipient for many profiles: search by name or Rufname; without a search the ★ favourites and the
/// last ones written to come first. Only profiles that take messages from me are listed (the Spark's list).
struct RecipientPicker: View {
    @ObservedObject var m: MessagesModel
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    private var hits: [Recipient] {
        let s = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !s.isEmpty else { return m.box.to }
        return m.box.to.filter { $0.name.lowercased().contains(s) || $0.call.lowercased().contains(s) }
    }

    private func pick(_ id: String) {
        m.to = id
        dismiss()
    }

    @ViewBuilder private func row(_ r: Recipient) -> some View {
        HStack {
            Button { pick(r.id) } label: {
                HStack {
                    Text(verbatim: r.label).foregroundStyle(.primary)
                    Spacer()
                    if m.to == r.id { Image(systemName: "checkmark").foregroundStyle(.tint) }
                }
            }
            Button { Task { await m.toggleFavourite(r.id) } } label: {
                Image(systemName: m.box.fav.contains(r.id) ? "star.fill" : "star")
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(Text("Favorit"))
        }
    }

    var body: some View {
        List {
            if search.isEmpty {
                let favs = m.box.fav.compactMap { id in m.box.to.first { $0.id == id } }
                let recent = m.box.recent.filter { !m.box.fav.contains($0) }.compactMap { id in m.box.to.first { $0.id == id } }
                if !favs.isEmpty { Section("Favoriten") { ForEach(favs) { row($0) } } }
                if !recent.isEmpty { Section("Zuletzt") { ForEach(recent) { row($0) } } }
                if m.box.all { Section { Button("Alle") { pick("all") } } }
            }
            Section {
                ForEach(hits) { row($0) }
                if hits.isEmpty { Text("Niemand passt.").foregroundStyle(.secondary) }
            } header: {
                Text("\(m.box.to.count) erreichbar")
            }
        }
        .searchable(text: $search, prompt: Text("Name oder Rufname"))
        .navigationTitle("An")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Why messages do or do not go through: the Spark's own check, the same as under Ich → Nachrichten.
struct ReadyView: View {
    let r: MessageReady
    @State var open: Bool
    static let few = 8

    @ViewBuilder private var offList: some View {
        ForEach(Array(r.off.enumerated()), id: \.offset) { _, x in
            LabeledContent { Text(verbatim: x.why).foregroundStyle(.secondary) } label: { Text(verbatim: x.name) }
        }
    }

    var body: some View {
        Section {
            DisclosureGroup(isExpanded: $open) {
                Label(r.enabled ? LocalizedStringKey("Vom Admin erlaubt") : LocalizedStringKey("Vom Admin ausgeschaltet"),
                      systemImage: r.enabled ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(r.enabled ? .green : .red)
                if r.enabled {
                    Label(r.on ? LocalizedStringKey("Für dich an") : LocalizedStringKey("Für dich aus"), systemImage: r.on ? "checkmark.circle.fill" : "xmark.circle")
                        .foregroundStyle(r.on ? .green : .red)
                }
                if let why = r.why { Text(verbatim: why).font(.footnote) }
                // with many profiles: the numbers, the names one tap further
                if r.reach.count > Self.few {
                    DisclosureGroup {
                        ForEach(r.reach) { Text(verbatim: $0.name) }
                    } label: { LabeledContent("Erreichbar") { Text(verbatim: "\(r.reach.count)") } }
                } else if !r.reach.isEmpty {
                    LabeledContent("Erreichbar") { Text(verbatim: r.reach.map(\.name).joined(separator: ", ")) }
                }
                if r.off.count > Self.few {
                    DisclosureGroup {
                        offList
                    } label: { LabeledContent("Nicht erreichbar") { Text(verbatim: "\(r.off.count)") } }
                } else {
                    offList
                }
                if !r.on || !r.enabled {
                    Text("Einschalten im Panel unter Ich → Nachrichten. Den Schalter für alle setzt der Admin unter Einstellungen → Funktionen.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            } label: {
                Text("Bereit?")
            }
        }
    }
}
