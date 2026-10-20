import SwiftUI

/// „Für dich“ (fuerdich.py, plan persoenlicher-assistent, stage 2): what the Spark found in the own mails by fixed
/// rules, the same list as E-Mail → Für dich in the panel (GET api/profile/fuerdich). The buttons are the ones the
/// Spark allows for a card (acts): Erinnern sets a reminder with a fixed text, Eintragen reads a fixed line like
/// „Schnell eintragen“ (only its „Eintragen“ saves), Antwort and Kündigung open the mail form, where only the preview
/// sends. Sender names and subjects are outside text: shown verbatim, never as a link.
struct FuerItem: Identifiable, Hashable {
    let id: String
    let kind: String
    let urgent: Bool
    let title: String
    let line: String
    let who: String
    let subject: String
    let ref: String
    let addr: String
    let event: String
    let acts: [String]
    let fits: String

    init(_ d: [String: Any]) {
        id = d["id"] as? String ?? ""
        kind = d["kind"] as? String ?? ""
        urgent = d["urgent"] as? Bool ?? false
        title = String((d["title"] as? String ?? "").prefix(200))
        line = String((d["line"] as? String ?? "").prefix(300))
        who = String((d["who"] as? String ?? "").prefix(60))
        subject = String((d["subject"] as? String ?? "").prefix(120))
        ref = d["ref"] as? String ?? ""
        addr = String((d["addr"] as? String ?? "").prefix(200))
        event = String((d["event"] as? String ?? "").prefix(200))
        acts = d["acts"] as? [String] ?? []
        fits = String((d["fits"] as? String ?? "").prefix(40))
    }

    var icon: String {
        ["verdacht": "exclamationmark.shield", "rechnung": "doc.text", "vertrag": "signature", "antwort": "envelope",
         "bestellung": "shippingbox", "angebot": "tag"][kind] ?? "envelope"
    }
}

@MainActor
final class FuerModel: ObservableObject {
    @Published var items: [FuerItem] = []
    @Published var loading = false
    @Published var nomail = false
    @Published var waiting = false
    @Published var errors: [String] = []
    @Published var error: String?
    @Published var note: String?
    @Published var month = ""
    @Published var tip: WissTip?

    func load(_ fresh: Bool = false) async {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); return }
        loading = true
        defer { loading = false }
        do {
            let d = try await api.object("GET", "api/profile/fuerdich", query: fresh ? ["fresh": "1"] : [:], timeout: 90)
            nomail = d["nomail"] as? Bool ?? false
            waiting = d["loading"] as? Bool ?? false
            if !waiting { items = (d["items"] as? [[String: Any]] ?? []).prefix(60).map(FuerItem.init) }
            errors = (d["errors"] as? [String] ?? []).prefix(5).map { String($0.prefix(120)) }
            month = String(((d["month"] as? [String: Any])?["line"] as? String ?? "").prefix(200))
            tip = WissTip(d["tip"] as? [String: Any])
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func mark(_ x: FuerItem, _ how: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("POST", "api/profile/fuerdich/mark", body: ["id": x.id, "as": how])
            items.removeAll { $0.id == x.id }
            note = how == "done" ? String(localized: "Als erledigt markiert.") : String(localized: "Kommt nicht wieder.")
        } catch {
            note = error.localizedDescription
        }
    }

    func remind(_ x: FuerItem) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/fuerdich/act", body: ["id": x.id, "do": "remind"])
            let due = Date(timeIntervalSince1970: ((d["due"] as? NSNumber)?.doubleValue ?? 0) / 1000)
            note = String(localized: "Erinnerung gesetzt: \(d["text"] as? String ?? "") · \(due.formatted(date: .abbreviated, time: .shortened))")
        } catch {
            note = error.localizedDescription
        }
    }

    /// „Mehr davon“ (stage 3): the shop of an order or offer becomes a confirmed interest (Was ich über dich weiß).
    func more(_ x: FuerItem) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/fuerdich/act", body: ["id": x.id, "do": "more"])
            note = String(localized: "Gemerkt: „\(d["name"] as? String ?? x.who)“ interessiert dich.")
            await load()
        } catch {
            note = error.localizedDescription
        }
    }

    func cancelDraft(_ x: FuerItem) async -> MailDraft? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("POST", "api/profile/fuerdich/act", body: ["id": x.id, "do": "cancel"])
            return MailDraft(to: d["to"] as? String ?? "", subject: d["subject"] as? String ?? "", text: d["text"] as? String ?? "")
        } catch {
            note = error.localizedDescription
            return nil
        }
    }

    func forget() async {
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("DELETE", "api/profile/fuerdich")
            await load(true)
        } catch {
            note = error.localizedDescription
        }
    }
}

struct FuerEvent: Identifiable {
    let line: String
    var id: String { line }
}

struct FuerDichView: View {
    @StateObject private var m = FuerModel()
    @State private var writing: MailDraft?
    @State private var adding: FuerEvent?
    @State private var asking = false

    var body: some View {
        List {
            Section {
                Text("Was der Spark in deinen Mails gefunden hat, nach festen Regeln. Die Mails bleiben ungelesen und unverändert; Links aus Mails öffnet der Spark nie.")
                    .font(.footnote).foregroundStyle(.secondary)
                if let n = m.note { Text(verbatim: n).font(.footnote) }
                NavigationLink { IchWeissView() } label: { Label("Was ich über dich weiß", systemImage: "person.text.rectangle") }
            }
            if m.nomail {
                Text(SparkAPI.way(String(localized: "Erst im Panel unter E-Mail → Einstellungen ein Postfach verbinden."))).foregroundStyle(.secondary)
            } else if m.waiting && m.items.isEmpty {
                Text("Lese deine Mails … das dauert beim ersten Mal etwas.").foregroundStyle(.secondary)
            } else if !m.loading && m.items.isEmpty && m.error == nil {
                Text("Gerade nichts, was dich braucht.").foregroundStyle(.secondary)
            }
            let urgent = m.items.filter(\.urgent), rest = m.items.filter { !$0.urgent }
            if !urgent.isEmpty { Section("Braucht dich") { ForEach(urgent) { row($0) } } }
            if !rest.isEmpty { Section("Gut zu wissen") { ForEach(rest) { row($0) } } }
            if !m.month.isEmpty || m.tip != nil {
                Section("Diesen Monat") {
                    if !m.month.isEmpty { Text(verbatim: m.month).font(.subheadline) }
                    if let tip = m.tip {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: tip.title)
                            Text("Tipp aus dem Netz zu „\(tip.name)“ · \(tip.domain)").font(.caption).foregroundStyle(.secondary)
                            if let u = tip.url { Link("Öffnen", destination: u).font(.callout) }
                        }
                    }
                }
            }
            if !m.errors.isEmpty { Text("Postfach nicht lesbar: \(m.errors.joined(separator: ", "))").foregroundStyle(.red) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Für dich")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button { Task { await m.load(true) } } label: { Label("Neu lesen", systemImage: "arrow.clockwise") }
                    Button(role: .destructive) { asking = true } label: { Label("Markierungen vergessen", systemImage: "arrow.uturn.backward") }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .confirmationDialog("Alle als erledigt oder uninteressant markierten Karten wieder zeigen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Markierungen vergessen", role: .destructive) { Task { await m.forget() } }
        }
        .overlay { if m.loading && m.items.isEmpty { ProgressView() } }
        .refreshable { await m.load(true) }
        .task {
            await m.load()
            // the first reading may still run on the Spark: asked again a few times, like the panel (fuerdich.js)
            var tries = 0
            while m.waiting && tries < 5 {
                tries += 1
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await m.load()
            }
        }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
        .sheet(item: $adding) { e in
            NavigationStack {
                List { Section("Eintragen") { QuickAdd(text: e.line) { _, _ in adding = nil } } }
                    .navigationTitle("Eintragen")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { adding = nil } } }
            }
        }
    }

    private func row(_ x: FuerItem) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: x.icon).foregroundStyle(x.urgent ? AnyShapeStyle(Color.orange) : AnyShapeStyle(.tint)).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: x.title).font(.headline)
                if !x.line.isEmpty { Text(verbatim: x.line).font(.subheadline).foregroundStyle(.secondary) }
                Text(verbatim: x.who + (x.subject.isEmpty ? "" : " · „" + x.subject + "“")).font(.caption).foregroundStyle(.secondary)
                if !x.fits.isEmpty { Text("passt zu „\(x.fits)“").font(.caption).foregroundStyle(.tint) }
                if !x.acts.isEmpty {
                    HStack(spacing: 14) {
                        if x.acts.contains("remind") { Button("Erinnern") { Task { await m.remind(x) } } }
                        if x.acts.contains("event") && !x.event.isEmpty { Button("Eintragen") { adding = FuerEvent(line: x.event) } }
                        if x.acts.contains("reply") {
                            Button("Antwort entwerfen") {
                                writing = MailDraft(reply: x.ref, to: x.addr, subject: x.subject.lowercased().hasPrefix("re:") ? x.subject : "Re: " + x.subject)
                            }
                        }
                        if x.acts.contains("cancel") {
                            Button("Kündigung entwerfen") { Task { writing = await m.cancelDraft(x) } }
                        }
                        if x.acts.contains("more") { Button("Mehr davon") { Task { await m.more(x) } } }
                    }
                    .font(.callout)
                    .buttonStyle(.borderless)
                    .padding(.top, 4)
                }
            }
        }
        .swipeActions(edge: .trailing) {
            Button { Task { await m.mark(x, "done") } } label: { Label("Erledigt", systemImage: "checkmark") }.tint(.green)
            Button { Task { await m.mark(x, "no") } } label: {
                x.kind == "verdacht" ? Label("Ist echt", systemImage: "hand.thumbsup") : Label("Nicht interessant", systemImage: "xmark")
            }
            .tint(.gray)
        }
    }
}
