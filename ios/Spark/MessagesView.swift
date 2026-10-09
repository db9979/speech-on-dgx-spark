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
                if to.isEmpty || !(b.to.contains { $0.id == to } || (to == "all" && b.all)) { to = b.to.first?.id ?? "" }
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
                Picker("An", selection: $m.to) {
                    ForEach(m.box.to) { r in Text(verbatim: r.name).tag(r.id) }
                    if m.box.all { Text("Alle").tag("all") }
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

/// Why messages do or do not go through: the Spark's own check, the same as under Ich → Nachrichten.
struct ReadyView: View {
    let r: MessageReady
    @State var open: Bool

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
                if !r.reach.isEmpty {
                    LabeledContent("Erreichbar") { Text(verbatim: r.reach.map(\.name).joined(separator: ", ")) }
                }
                ForEach(Array(r.off.enumerated()), id: \.offset) { _, x in
                    LabeledContent { Text(verbatim: x.why).foregroundStyle(.secondary) } label: { Text(verbatim: x.name) }
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
