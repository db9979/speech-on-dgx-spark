import SwiftUI
import UIKit

/// Alles Offene im Assistenten (vorgaenge.py, plan assistent-zentrale Stufe 1): the same Vorgänge as the panel's page
/// Offen. A message of the conversation carries only the number ("vg"); the card is drawn from this store, so a button
/// pressed in the browser changes the card here at the next look. The buttons are names the Spark sent and the Spark
/// checks each again (rev: another device was quicker → the card shows the new state). Titles are the panel's words,
/// a sender from a mail is outside text: shown with Text(verbatim:) only. Opens with the admin's release
/// (iphone.THINGS "vorgaenge").
struct Vorgang: Identifiable {
    struct Knopf: Hashable {
        let k: String
        let name: String
        let page: Bool
    }
    let id: String
    let art: String
    let artName: String
    /// the kind's picture (vorgaenge.ARTEN sym): bell, check, mail, chat, share, warn, spark
    let sym: String
    let urgent: Bool
    let title: String
    let line: String
    let facts: [(String, String)]
    let due: String
    let state: String
    let group: String
    let laterUntil: Date?
    let how: String
    let place: String
    let changed: Date?
    let made: Date?
    let rev: Int
    let knoepfe: [Knopf]
    let data: [String: String]
    /// a proposal's card (Stufe 2): what it says after its yes („Eingetragen“, „Gesendet“)
    let fertig: String

    init(_ d: [String: Any], en: Bool) {
        let date = { (k: String) -> Date? in
            let t = (d[k] as? NSNumber)?.doubleValue ?? 0
            return t > 0 ? Date(timeIntervalSince1970: t) : nil
        }
        id = d["id"] as? String ?? ""
        art = d["art"] as? String ?? ""
        artName = (en ? d["art_en"] : d["art_de"]) as? String ?? ""
        sym = d["sym"] as? String ?? "mail"
        urgent = d["dringend"] as? Bool ?? false
        title = String((d["titel"] as? String ?? "").prefix(200))
        line = String((d["zeile"] as? String ?? "").prefix(200))
        facts = (d["felder"] as? [[String]] ?? []).compactMap { $0.count == 2 ? ($0[0], $0[1]) : nil }
        due = d["frist"] as? String ?? ""
        state = d["zustand"] as? String ?? ""
        group = d["gruppe"] as? String ?? ""
        laterUntil = date("spaeter_bis")
        how = d["wie"] as? String ?? ""
        place = d["wo"] as? String ?? ""
        changed = date("ge")
        made = date("t")
        rev = d["rev"] as? Int ?? 0
        knoepfe = (d["acts"] as? [[String: Any]] ?? []).map {
            Knopf(k: $0["k"] as? String ?? "", name: (en ? $0["en"] : $0["de"]) as? String ?? "", page: $0["stufe"] as? String == "seite")
        }
        data = d["daten"] as? [String: String] ?? [:]
        let f = d["fertig"] as? [String] ?? []
        fertig = f.count == 2 ? (en ? f[1] : f[0]) : ""
    }

    var done: Bool { group == "erledigt" }
    func has(_ k: String) -> Bool { knoepfe.contains { $0.k == k } }
}

@MainActor
final class VorgangStore: ObservableObject {
    static let shared = VorgangStore()
    static let en = Locale.current.language.languageCode?.identifier != "de"
    @Published var items: [String: Vorgang] = [:]
    @Published var counts: [String: Int] = [:]
    @Published var later: [(String, String)] = []
    @Published var error: String?
    @Published var loading = false
    private var rev = 0
    private var asked = Date.distantPast

    func load(all: Bool = false) async {
        guard Conversation.shared.allowed.areas.contains("vorgaenge"), let api = SparkAPI.current else { return }
        loading = true
        defer { loading = false }
        do {
            let d = try await api.object("GET", "/api/profile/vorgaenge", query: ["seit": all ? "0" : String(rev)])
            if all { items = [:] }
            for x in (d["items"] as? [[String: Any]] ?? []).map({ Vorgang($0, en: Self.en) }) { items[x.id] = x }
            rev = d["rev"] as? Int ?? rev
            counts = d["counts"] as? [String: Int] ?? counts
            let order = ["abend", "morgen", "woche", "ohne"], sp = d["spaeter"] as? [String: [String]] ?? [:]
            later = order.compactMap { k in sp[k].map { (k, Self.en ? $0.last ?? k : $0.first ?? k) } }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// a card of the conversation shows: one look for what changed, at most every 10 seconds for an unknown number and
    /// every 30 seconds otherwise (a button pressed in the browser shows here then)
    func want(_ id: String) {
        guard Date().timeIntervalSince(asked) > (items[id] == nil ? 10 : 30) else { return }
        asked = Date()
        Task { await load() }
    }

    func list(_ group: String) -> [Vorgang] {
        let xs = items.values.filter { $0.group == group }
        switch group {
        case "spaeter": return xs.sorted { ($0.laterUntil ?? .distantFuture) < ($1.laterUntil ?? .distantFuture) }
        case "erledigt": return xs.sorted { ($0.changed ?? .distantPast) > ($1.changed ?? .distantPast) }
        default: return xs.sorted { $0.urgent != $1.urgent ? $0.urgent : ($0.made ?? .distantPast) > ($1.made ?? .distantPast) }
        }
    }

    /// one button; the Spark answers with the card as it is now (and a draft for „Kündigung entwerfen …“)
    func act(_ x: Vorgang, _ k: String, when: String = "") async -> [String: Any]? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("POST", "/api/profile/vorgaenge/act", body: ["id": x.id, "act": k, "rev": x.rev, "wann": when])
            if let i = d["item"] as? [String: Any] { let y = Vorgang(i, en: Self.en); items[y.id] = y }
            error = nil
            await load()
            return d
        } catch {
            self.error = error.localizedDescription
            await load(all: true)        // another device was quicker: show the state it left
            return nil
        }
    }

    func drop(onlyDone: Bool) async {
        guard let api = SparkAPI.current else { return }
        _ = try? await api.object("DELETE", "/api/profile/vorgaenge", query: onlyDone ? ["nur": "erledigt"] : [:])
        await load(all: true)
    }
}

/// the picture of a kind (vorgaenge.ARTEN sym), the same set as the panel's offen.js
func vorgangSymbol(_ sym: String) -> String {
    ["bell": "bell", "check": "checkmark.seal", "chat": "bubble.left", "share": "square.and.arrow.up",
     "warn": "exclamationmark.triangle", "spark": "sparkles"][sym] ?? "envelope"
}

/// a chat the card „Antworten …“ opens (ChatsView starts in it)
struct ChatStart: Identifiable { let id: String }

/// the line under a card: what happened, where and when
func vorgangState(_ x: Vorgang) -> String {
    let f = Date.FormatStyle(date: .abbreviated, time: .shortened)
    if x.state == "spaeter" {
        return x.laterUntil.map { String(localized: "Später: wieder da \($0.formatted(f))") } ?? String(localized: "Später, ohne Zeit")
    }
    guard x.done else { return "" }
    let ended: [String: String] = ["vs_nein": String(localized: "Abgebrochen"), "vs_aendern": String(localized: "Weiter auf der Seite"),
                                   "beantwortet": String(localized: "Im Gespräch beantwortet"), "ersetzt": String(localized: "Neuer Vorschlag"),
                                   "fehler": String(localized: "Nicht ausgeführt"), "cx_gelesen": String(localized: "Gelesen"),
                                   "geantwortet": String(localized: "Beantwortet"), "bestaetigt": String(localized: "Bestätigt"),
                                   "abgelehnt": String(localized: "Abgelehnt"), "wieder_da": String(localized: "Läuft wieder")]
    let how = x.how == "abgelaufen" ? String(localized: "Abgelaufen") : x.how == "vs_ja" && !x.fertig.isEmpty ? x.fertig
        : ended[x.how] ?? (x.state == "weg" ? String(localized: "Nicht wichtig")
        : x.how == "fd_remind" ? String(localized: "Erinnerung gesetzt") : String(localized: "Erledigt"))
    return [how, x.place, x.changed?.formatted(f) ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
}

struct VorgangKarte: View {
    let x: Vorgang
    @ObservedObject var store = VorgangStore.shared
    @State private var busy = false
    @State private var writing: MailDraft?
    @State private var adding: FuerEvent?
    @State private var note: (String, Bool)?
    @State private var chat: ChatStart?
    @State private var reading: MailItem?
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if x.done {
                HStack {
                    Image(systemName: "checkmark.circle").foregroundStyle(.green)
                    Text(verbatim: x.title).lineLimit(1)
                    Spacer()
                    if x.has("zurueck") { Button("Zurückholen") { run("zurueck") }.font(.footnote) }
                }
                Text(verbatim: vorgangState(x)).font(.caption).foregroundStyle(.secondary)
                if let n = note { Text(verbatim: n.0).font(.caption).foregroundStyle(n.1 ? Color.secondary : Color.red) }
            } else {
                HStack(spacing: 6) {
                    Image(systemName: vorgangSymbol(x.sym)).foregroundStyle(.tint)
                    Text(verbatim: x.artName.uppercased()).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if !x.due.isEmpty { Text(verbatim: x.due).font(.caption).foregroundStyle(.orange) }
                }
                Text(verbatim: x.title).font(.headline)
                if !x.line.isEmpty { Text(verbatim: x.line).font(.subheadline).foregroundStyle(.secondary) }
                ForEach(x.facts.indices, id: \.self) { i in
                    LabeledContent(x.facts[i].0 == "Von" ? String(localized: "Von") : x.facts[i].0) { Text(verbatim: x.facts[i].1) }.font(.subheadline)
                }
                HStack {
                    ForEach(x.knoepfe.filter { $0.k != "spaeter" && $0.k != "zurueck" }.prefix(3), id: \.self) { b in
                        Button { run(b.k, page: b.page) } label: { Text(verbatim: b.name).lineLimit(1) }
                            .buttonStyle(.bordered)
                    }
                    if x.state == "spaeter" && x.has("zurueck") { Button("Jetzt zeigen") { run("zurueck") }.buttonStyle(.bordered) }
                    if x.has("spaeter") {
                        Menu {
                            ForEach(store.later, id: \.0) { w in Button { run("spaeter", when: w.0) } label: { Text(verbatim: w.1) } }
                        } label: { Text("Später") }
                        .buttonStyle(.bordered)
                    }
                }
                .disabled(busy)
                .font(.footnote)
                let st = vorgangState(x)
                if !st.isEmpty { Text(verbatim: st).font(.caption).foregroundStyle(.secondary) }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(.secondarySystemBackground)))
        .overlay(alignment: .leading) { if x.urgent && !x.done { Rectangle().fill(.orange).frame(width: 3).clipShape(Capsule()) } }
        .sheet(item: $writing) { d in MailWrite(draft: d) }
        .sheet(item: $chat) { c in ChatsView(start: c.id) }
        .sheet(item: $reading) { m in NavigationStack { MailView(item: m, box: "", folder: nil, post: PostModel()) } }
        .sheet(item: $adding) { e in
            NavigationStack {
                List { Section("Eintragen") { QuickAdd(text: e.line) { _, _ in adding = nil } } }
                    .navigationTitle("Eintragen")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { adding = nil } } }
            }
        }
    }

    /// "seite": the place where the person goes on opens here (nothing is sent or saved by the button itself)
    private func run(_ k: String, page: Bool = false, when: String = "") {
        busy = true
        Task {
            let d = await store.act(x, k, when: when)
            busy = false
            if let t = d?["text"] as? String, !t.isEmpty { note = (t, d?["gelungen"] as? Bool ?? false) }   // a proposal's yes
            guard page, let d else { return }
            let z = x.data
            switch k {
            case "fd_event": if let e = z["event"], !e.isEmpty { adding = FuerEvent(line: e) }
            case "fd_reply":
                let s = z["subject"] ?? ""
                writing = MailDraft(reply: z["ref"] ?? "", to: z["addr"] ?? "", subject: s.lowercased().hasPrefix("re:") ? s : "Re: " + s,
                                    folder: z["folder"] ?? "INBOX")
            case "fd_cancel":
                if let m = d["draft"] as? [String: Any] {
                    writing = MailDraft(to: m["to"] as? String ?? "", subject: m["subject"] as? String ?? "", text: m["text"] as? String ?? "")
                }
            case "vs_aendern":   // the proposal goes to the form or the writing window, filled; only there it is saved or sent
                if let e = d["event"] as? String, !e.isEmpty { adding = FuerEvent(line: e) }
                if let m = d["draft"] as? [String: Any] {
                    writing = MailDraft(to: m["to"] as? String ?? "", subject: m["subject"] as? String ?? "", text: m["text"] as? String ?? "")
                }
            case "oeffnen":   // stages 3+4: only the place in the panel where it goes on (a fixed way, Sprung-Link)
                if let w = z["weg"], let u = SparkAPI.wayLink(w) { openURL(u) }
            case "cx_antworten": if let c = z["chat"], !c.isEmpty { chat = ChatStart(id: c) }
            case "ml_lesen":
                if let r = z["ref"], !r.isEmpty {
                    reading = MailItem(id: r, from: z["addr"] ?? "", subject: z["subject"] ?? "", date: x.made ?? Date(), unread: false, box: 0)
                }
            default: break
            }
        }
    }
}

/// the card „Wartet auf dein Ja“ under the answer that made the proposal (Stufe 2), the Ja/Nein card until it is known
struct VorschlagKarte: View {
    let id: String
    let kind: String
    @ObservedObject private var store = VorgangStore.shared

    var body: some View {
        if let x = store.items[id] {
            VorgangKarte(x: x).frame(maxWidth: 420, alignment: .leading)
        } else {
            ConfirmCard(kind: kind).onAppear { store.want(id) }
        }
    }
}

/// a message of the conversation with "vg": its card, or the sentence while the store does not know it (switched off,
/// or older than the Erledigt days)
struct VorgangImGespraech: View {
    let id: String
    let message: Conversation.Message
    @ObservedObject private var store = VorgangStore.shared

    var body: some View {
        if let x = store.items[id] {
            VorgangKarte(x: x).frame(maxWidth: 420, alignment: .leading).onAppear { store.want(id) }
        } else {
            Bubble(message: message).onAppear { store.want(id) }
        }
    }
}

/// Meine Sachen → Offen: Braucht dich, Später, Erledigt (7 Tage), like the panel's page Offen
struct OffenView: View {
    @ObservedObject private var store = VorgangStore.shared
    @State private var group = "braucht"
    @State private var asking = false

    var body: some View {
        List {
            Picker("Gruppe", selection: $group) {
                Text("Braucht dich \(store.counts["braucht"] ?? 0)").tag("braucht")
                Text("Später \(store.counts["spaeter"] ?? 0)").tag("spaeter")
                Text("Erledigt \(store.counts["erledigt"] ?? 0)").tag("erledigt")
            }
            .pickerStyle(.segmented)
            .listRowBackground(Color.clear)
            let xs = store.list(group)
            if xs.isEmpty && !store.loading {
                Text(group == "braucht" ? "Nichts offen. Was dich braucht, kommt als Karte ins Gespräch und steht dann hier."
                     : group == "spaeter" ? "Nichts für später." : "In den letzten 7 Tagen nichts erledigt.")
                    .foregroundStyle(.secondary)
            }
            ForEach(xs) { x in VorgangKarte(x: x).listRowInsets(EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12)) }
            if let e = store.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            Section {
                Button("Erledigte entfernen") { Task { await store.drop(onlyDone: true) } }
                Button("Alles löschen", role: .destructive) { asking = true }
            } footer: {
                Text(SparkAPI.way(String(localized: "Mails und Erinnerungen bleiben, wo sie sind. Ob eine Karte auch als Mitteilung kommt, stellst du unter Ich → Von selbst ein.")))
            }
        }
        .navigationTitle("Offen")
        .confirmationDialog("Alles Offene löschen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Alles löschen", role: .destructive) { Task { await store.drop(onlyDone: false) } }
        }
        .refreshable { await store.load(all: true) }
        .task { await store.load(all: true) }
    }
}

/// Mitteilung antippen öffnet genau diese Meldung (mitteilungen.py, Dominik 2026-10-23): a tapped note with what its
/// card offers. The Spark picks the target by fixed rules (ziel); the app only shows it and checks the forms.
struct Mitteilung: Identifiable {
    let id: String
    let title: String
    let body: String
    /// nil: the note is gone (older than a day, or the Spark restarted)
    let at: Date?
    let art: String
    let vg: String
    let chat: String
    let ref: String
    let code: String
    let weg: String

    static func gone(_ id: String) -> Mitteilung {
        Mitteilung(id: id, title: "", body: "", at: nil, art: "text", vg: "", chat: "", ref: "", code: "", weg: "")
    }
}

extension SparkAPI {
    /// The tapped note by its number (GET /api/iphone/note with tapped=1); nil when the Spark no longer has it.
    func mitteilung(_ id: String) async -> Mitteilung? {
        guard let d = try? await object("GET", "api/iphone/note", query: ["id": id, "tapped": "1"]),
              let title = d["title"] as? String, let body = d["body"] as? String else { return nil }
        let z = d["ziel"] as? [String: Any] ?? [:]
        func pick(_ k: String, _ rx: String) -> String {
            let v = z[k] as? String ?? ""
            return v.range(of: rx, options: .regularExpression) != nil ? v : ""
        }
        return Mitteilung(id: id, title: String(title.prefix(200)), body: String(body.prefix(1500)),
                          at: (d["t"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) } ?? Date(),
                          art: pick("art", "^[a-z]{3,8}$"), vg: pick("vg", "^v[0-9a-f]{10}$"), chat: pick("chat", "^c[0-9a-f]{12}$"),
                          ref: pick("ref", "^m[0-9a-f]{8}:[0-9]{1,10}$"), code: pick("code", "^[A-Z0-9]{4,8}$"),
                          weg: String((z["weg"] as? String ?? "").prefix(200)))
    }
}

/// the tapped note above the conversation: its whole text (a way in it is a Sprung-Link) and the one button that fits
struct MitteilungKarte: View {
    let x: Mitteilung
    @ObservedObject private var store = VorgangStore.shared
    @State private var chat: ChatStart?
    @State private var reading: MailItem?
    @State private var copied = false
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "bell").foregroundStyle(.tint)
                Text("Mitteilung").textCase(.uppercase).font(.caption).foregroundStyle(.secondary)
                Spacer()
                if let at = x.at { Text(verbatim: at.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary) }
                Button { Conversation.shared.tapped = nil } label: { Image(systemName: "xmark") }
                    .buttonStyle(.borderless).accessibilityLabel(Text("Schließen"))
            }
            if x.at == nil {
                Text("Diese Mitteilung ist nicht mehr da (älter als ein Tag oder nach einem Neustart des Spark).")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else {
                Text(verbatim: x.title).font(.headline)
                Text(SparkAPI.way(x.body)).font(.subheadline).textSelection(.enabled)
                if x.art == "vorgang", let v = store.items[x.vg] { VorgangKarte(x: v) }
                HStack {
                    if x.art == "chat" { Button("Chat öffnen") { chat = ChatStart(id: x.chat) }.buttonStyle(.borderedProminent) }
                    if x.art == "mail" {
                        Button("Mail lesen") {
                            reading = MailItem(id: x.ref, from: "", subject: x.body, date: x.at ?? Date(), unread: false, box: 0)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    if x.art == "code" {
                        Button {
                            UIPasteboard.general.setItems([[UIPasteboard.typeAutomatic: x.code]],
                                                          options: [.expirationDate: Date().addingTimeInterval(180), .localOnly: true])
                            copied = true
                        } label: { copied ? Text("Kopiert") : Text("Code kopieren") }
                        .buttonStyle(.borderedProminent)
                    }
                    if !x.weg.isEmpty, let u = SparkAPI.wayLink(x.weg) {
                        Button { openURL(u) } label: { Text("Öffnen: \(x.weg)").lineLimit(1) }.buttonStyle(.bordered)
                    }
                }
                .font(.footnote)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(.secondarySystemBackground)))
        .overlay(alignment: .leading) { Rectangle().fill(.tint).frame(width: 3).clipShape(Capsule()) }
        .onAppear { if x.art == "vorgang" { store.want(x.vg) } }
        .sheet(item: $chat) { c in ChatsView(start: c.id) }
        .sheet(item: $reading) { m in NavigationStack { MailView(item: m, box: "", folder: nil, post: PostModel()) } }
    }
}
