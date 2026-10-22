import SwiftUI

/// „Was ich über dich weiß“ (ichweiss.py, plan persoenlicher-assistent, stages 3 and 4): the same page as Ich → Was ich
/// über dich weiß in the panel (GET api/profile/ichweiss). Interests count only after „Stimmt“; „Nicht so“ is
/// remembered; what comes back every month gets „Monatlich erinnern“; the week and this month's sum come from checked
/// values. Shop names, subjects and web titles are outside text: shown verbatim; the web tip opens only as an https link.
/// Proposals are topics (plan interessen-themen): the senders and up to three subjects as evidence, „Thema unklar“ with
/// an own topic, older confirmed senders asked once for their topic.
private var wissEnglish: Bool { Locale.current.language.languageCode?.identifier == "en" }

struct WissInterest: Identifiable, Hashable {
    let name: String
    let en: String
    let state: String
    let web: Bool
    let src: String
    let senders: [String]
    var id: String { name.lowercased() }
    var label: String { wissEnglish && !en.isEmpty ? en : name }

    init(_ d: [String: Any]) {
        name = String((d["name"] as? String ?? "").prefix(40))
        en = String((d["en"] as? String ?? "").prefix(40))
        state = d["state"] as? String ?? ""
        web = d["web"] as? Bool ?? false
        src = d["src"] as? String ?? "hand"
        senders = (d["senders"] as? [String] ?? []).prefix(20).map { String($0.prefix(40)) }
    }
}

struct WissProposal: Identifiable, Hashable {
    let name: String
    let en: String
    let src: String
    let why: String
    let topic: String
    let senders: [String]
    let examples: [String]
    let unclear: Bool
    var id: String { name.lowercased() }
    var label: String { wissEnglish && !en.isEmpty ? en : name }

    init(_ d: [String: Any]) {
        name = String((d["name"] as? String ?? "").prefix(40))
        en = String((d["en"] as? String ?? "").prefix(40))
        src = d["src"] as? String ?? "hand"
        why = String((d["why"] as? String ?? "").prefix(120))
        topic = String((d["topic"] as? String ?? "").prefix(40))
        senders = (d["senders"] as? [String] ?? []).prefix(20).map { String($0.prefix(40)) }
        examples = (d["ex"] as? [String] ?? []).prefix(3).map { String($0.prefix(80)) }
        unclear = d["unclear"] as? Bool ?? false
    }
}

/// A topic to pick for „Thema unklar“: the confirmed interests first, then the fixed list (choices in ichweiss.py).
struct WissChoice: Identifiable, Hashable {
    let name: String
    let label: String
    var id: String { name.lowercased() }

    init(_ d: [String: Any]) {
        name = String((d["name"] as? String ?? "").prefix(40))
        let en = String((d["en"] as? String ?? "").prefix(40))
        label = wissEnglish && !en.isEmpty ? en : name
    }
}

/// 6a: an older confirmed sender and the topic the last reading found for it.
struct WissAsk: Identifiable, Hashable {
    let name: String
    let topic: String
    let label: String
    var id: String { name.lowercased() }

    init(_ d: [String: Any]) {
        name = String((d["name"] as? String ?? "").prefix(40))
        topic = String((d["topic"] as? String ?? "").prefix(40))
        let de = String((d["label"] as? String ?? "").prefix(40)), en = String((d["en"] as? String ?? "").prefix(40))
        label = wissEnglish && !en.isEmpty ? en : de
    }
}

struct WissRecurring: Identifiable, Hashable {
    let id: String
    let who: String
    let day: Int
    let months: Int
    let set: Bool

    init(_ d: [String: Any]) {
        id = d["id"] as? String ?? ""
        who = String((d["who"] as? String ?? "").prefix(60))
        day = d["day"] as? Int ?? 0
        months = d["months"] as? Int ?? 0
        set = d["set"] as? Bool ?? false
    }
}

/// The tip from the web (4a): its address only when it is https, else no link.
struct WissTip: Hashable {
    let name: String
    let title: String
    let domain: String
    let url: URL?

    init?(_ d: [String: Any]?) {
        guard let d, let u = d["url"] as? String, !u.isEmpty else { return nil }
        name = String((d["name"] as? String ?? "").prefix(40))
        title = String((d["title"] as? String ?? "").prefix(120))
        domain = String((d["domain"] as? String ?? "").prefix(80))
        let url = URL(string: u)
        self.url = url?.scheme == "https" ? url : nil
    }
}

@MainActor
final class WissModel: ObservableObject {
    @Published var interests: [WissInterest] = []
    @Published var proposals: [WissProposal] = []
    @Published var asks: [WissAsk] = []
    @Published var choices: [WissChoice] = []
    @Published var recurring: [WissRecurring] = []
    @Published var week = ""
    @Published var month = ""
    @Published var tip: WissTip?
    @Published var tips = false
    @Published var facts = 0
    @Published var styleMails = 0
    @Published var loading = false
    @Published var waiting = false
    @Published var error: String?
    @Published var note: String?

    func load() async {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); return }
        loading = true
        defer { loading = false }
        do {
            let d = try await api.object("GET", "api/profile/ichweiss", timeout: 60)
            interests = (d["interests"] as? [[String: Any]] ?? []).prefix(60).map(WissInterest.init)
            proposals = (d["proposals"] as? [[String: Any]] ?? []).prefix(8).map(WissProposal.init)
            asks = (d["asks"] as? [[String: Any]] ?? []).prefix(8).map(WissAsk.init)
            choices = (d["choices"] as? [[String: Any]] ?? []).prefix(100).map(WissChoice.init)
            recurring = (d["recurring"] as? [[String: Any]] ?? []).prefix(30).map(WissRecurring.init)
            week = String(((d["week"] as? [String: Any])?["sentence"] as? String ?? "").prefix(400))
            month = String(((d["month"] as? [String: Any])?["line"] as? String ?? "").prefix(200))
            tip = WissTip(d["tip"] as? [String: Any])
            tips = d["tips"] as? Bool ?? false
            facts = (d["facts"] as? [String: Any])?["count"] as? Int ?? 0
            styleMails = (d["style"] as? [String: Any])?["mails"] as? Int ?? 0
            waiting = !(d["loading"] as? [String] ?? []).isEmpty
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func set(_ name: String, _ state: String, src: String = "hand", web: Bool? = nil, topic: String = "",
             senders: [String] = [], label: String? = nil) async {
        guard let api = SparkAPI.current else { return }
        var body: [String: Any] = ["name": name, "state": state, "src": src, "topic": topic, "senders": senders]
        if let web { body["web"] = web }
        do {
            _ = try await api.object("POST", "api/profile/ichweiss/interest", body: body)
            let shown = label ?? name
            note = state == "yes" || state == "adopt" ? String(localized: "Gemerkt: „\(shown)“ interessiert dich.")
                : state == "no" ? String(localized: "Kommt nicht wieder als Vorschlag.")
                : state == "keep" ? String(localized: "Bleibt, wie es ist.") : String(localized: "Vergessen.")
            await load()
        } catch {
            note = error.localizedDescription
        }
    }

    func remindMonthly(_ x: WissRecurring) async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("POST", "api/profile/ichweiss/recurring", body: ["id": x.id])
            note = d["again"] as? Bool == true ? String(localized: "Diese Erinnerung gibt es schon.")
                : String(localized: "Monatliche Erinnerung gesetzt: \(d["text"] as? String ?? "")")
            await load()
        } catch {
            note = error.localizedDescription
        }
    }

    func forget() async {
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("DELETE", "api/profile/ichweiss")
            await load()
        } catch {
            note = error.localizedDescription
        }
    }
}

struct IchWeissView: View {
    @StateObject private var m = WissModel()
    @State private var own = ""
    @State private var asking = false

    var body: some View {
        List {
            Section {
                Text("Was der Spark über dich weiß und woher: Interessen zählen erst, wenn du „Stimmt“ sagst. Feste Regeln, kein Modell, alles bleibt auf dem Spark.")
                    .font(.footnote).foregroundStyle(.secondary)
                if let n = m.note { Text(verbatim: n).font(.footnote) }
            }
            Section("Diese Woche") {
                if !m.week.isEmpty { Text(verbatim: m.week) }
                if !m.month.isEmpty { Text(verbatim: m.month).font(.subheadline).foregroundStyle(.secondary) }
            }
            if !m.proposals.isEmpty {
                Section("Vorschläge") {
                    ForEach(m.proposals) { x in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(verbatim: x.label).font(.headline)
                                if x.unclear { Text("Thema unklar").font(.caption2).foregroundStyle(.orange) }
                            }
                            Text("Beleg: \(x.why)").font(.caption).foregroundStyle(.secondary)
                            if !x.unclear && !x.senders.isEmpty {
                                Text(verbatim: x.senders.joined(separator: " · ")).font(.caption)
                            }
                            if !x.unclear && !x.examples.isEmpty {
                                Text(verbatim: x.examples.map { "„\($0)“" }.joined(separator: ", ")).font(.caption).italic().foregroundStyle(.secondary)
                            }
                            if x.unclear { WissOwnTopic(sender: x.name, examples: x.examples, m: m) }
                            HStack(spacing: 16) {
                                Button("Stimmt") { Task { await m.set(x.name, "yes", src: x.src, topic: x.topic, senders: x.senders, label: x.label) } }
                                Button("Nicht so") { Task { await m.set(x.name, "no", src: x.src, topic: x.topic) } }
                                if !x.unclear && !x.senders.isEmpty {
                                    Menu("Absender") {
                                        ForEach(x.senders, id: \.self) { n in
                                            Button("Nicht „\(n)“") { Task { await m.set(n, "no", src: "shop") } }
                                        }
                                    }
                                }
                            }
                            .font(.callout).buttonStyle(.borderless)
                        }
                    }
                }
            }
            if !m.asks.isEmpty {
                Section("Zu welchem Thema gehört das?") {
                    ForEach(m.asks) { x in
                        VStack(alignment: .leading, spacing: 4) {
                            Text("„\(x.name)“ gehört wohl zu \(x.label)")
                            Text("Du hast den Absender früher bestätigt. Als Thema passen auch neue Absender, und der Netz-Tipp sucht nach dem Thema.")
                                .font(.caption).foregroundStyle(.secondary)
                            HStack(spacing: 16) {
                                Button("Übernehmen") { Task { await m.set(x.name, "adopt", topic: x.topic, label: x.label) } }
                                Button("So lassen") { Task { await m.set(x.name, "keep") } }
                            }
                            .font(.callout).buttonStyle(.borderless)
                        }
                    }
                }
            }
            Section("Interessen") {
                ForEach(m.interests.filter { $0.state == "yes" }) { x in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(verbatim: x.label)
                        if !x.senders.isEmpty {
                            Text("Absender: \(x.senders.joined(separator: ", "))").font(.caption).foregroundStyle(.secondary)
                        }
                        if m.tips {
                            Toggle("Tipps aus dem Netz", isOn: Binding(get: { x.web }, set: { v in Task { await m.set(x.name, "yes", src: x.src, web: v) } }))
                                .font(.caption)
                        }
                    }
                    .swipeActions { Button(role: .destructive) { Task { await m.set(x.name, "forget") } } label: { Label("Vergessen", systemImage: "trash") } }
                }
                HStack {
                    TextField("z. B. Rennrad", text: $own).onSubmit { add() }
                    Button("Hinzufügen") { add() }.disabled(own.trimmingCharacters(in: .whitespaces).count < 2)
                }
            }
            let no = m.interests.filter { $0.state == "no" }
            if !no.isEmpty {
                Section("Nicht so") {
                    ForEach(no) { x in
                        Text(verbatim: x.name)
                            .swipeActions { Button { Task { await m.set(x.name, "forget") } } label: { Label("Wieder vorschlagen dürfen", systemImage: "arrow.uturn.backward") } }
                    }
                }
            }
            if let tip = m.tip {
                Section("Aus dem Netz") {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: tip.title)
                        Text("Tipp zu „\(tip.name)“ · \(tip.domain)").font(.caption).foregroundStyle(.secondary)
                        if let u = tip.url { Link("Öffnen", destination: u).font(.callout) }
                    }
                }
            }
            Section("Wiederkehrendes") {
                if m.recurring.isEmpty {
                    Text(m.waiting ? String(localized: "Lese die Kopfzeilen deiner Mails …") : String(localized: "Nichts gefunden, was jeden Monat kommt.")).foregroundStyle(.secondary)
                }
                ForEach(m.recurring) { x in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Rechnung \(x.who) kommt um den \(x.day).")
                        Text("in \(x.months) Monaten").font(.caption).foregroundStyle(.secondary)
                        Button(x.set ? String(localized: "Erinnerung ist da") : String(localized: "Monatlich erinnern")) { Task { await m.remindMonthly(x) } }
                            .disabled(x.set).font(.callout).buttonStyle(.borderless)
                    }
                }
            }
            Section("Gemerkt") {
                Text("\(m.facts) gemerkte Fakten")
                Text(SparkAPI.way(String(localized: "Ändern und vergessen unter Ich → Gedächtnis"))).font(.caption).foregroundStyle(.secondary)
                if m.styleMails > 0 { Text("Mailstil aus \(m.styleMails) eigenen Mails gelernt") }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Was ich über dich weiß")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button(role: .destructive) { asking = true } label: { Label("Alle Interessen vergessen", systemImage: "trash") }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .confirmationDialog("Alle Interessen und den Tipp aus dem Netz vergessen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Alle Interessen vergessen", role: .destructive) { Task { await m.forget() } }
        }
        .overlay { if m.loading && m.interests.isEmpty && m.week.isEmpty { ProgressView() } }
        .refreshable { await m.load() }
        .task {
            await m.load()
            var tries = 0   // the headers of Wiederkehrendes may still be read on the Spark, like the panel (ichweiss.js)
            while m.waiting && tries < 5 {
                tries += 1
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                await m.load()
            }
        }
    }

    private func add() {
        let v = own.trimmingCharacters(in: .whitespaces)
        guard v.count >= 2 else { return }
        own = ""
        Task { await m.set(String(v.prefix(40)), "yes") }
    }
}

/// „Thema unklar“ (4a): the subjects as evidence and a field for an own topic that this sender belongs to.
struct WissOwnTopic: View {
    let sender: String
    let examples: [String]
    @ObservedObject var m: WissModel
    @State private var topic = ""

    var body: some View {
        DisclosureGroup("Betreffe zeigen und eigenes Thema") {
            ForEach(examples, id: \.self) { e in Text(verbatim: "„\(e)“").font(.caption).italic() }
            if !m.choices.isEmpty {
                Menu("Vorhandenes Thema wählen …") {
                    ForEach(m.choices) { c in
                        Button(c.label) { topic = c.name }
                    }
                }
            }
            HStack {
                TextField("oder eintippen, z. B. Wandern", text: $topic)
                Button("Als Thema merken") {
                    let v = String(topic.trimmingCharacters(in: .whitespaces).prefix(40))
                    guard v.count >= 2 else { return }
                    topic = ""
                    Task { await m.set(v, "yes", senders: [sender]) }
                }
                .disabled(topic.trimmingCharacters(in: .whitespaces).count < 2)
            }
        }
        .font(.caption)
    }
}
