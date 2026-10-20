import SwiftUI
import WidgetKit
import CoreImage.CIFilterBuiltins

/// Listen (plan listen-teilen.md, Dominik 2026-10-20 „1a 2a“): the same lists as the panel's page Listen (tasks.py):
/// Einkauf, Aufgaben and own lists, who put an entry on and from where, „Erledigt“ with „Zurückholen“, the shopping
/// list by departments. Opens with the admin's release of Listen (iphone.THINGS "tasks"); every rule stays on the Spark.
/// Listen teilen (Stufe 2): lists other profiles share show under „Mit mir geteilt“ with whose they are; „Sehen“ only
/// shows them, „Mitschreiben“ adds and ticks off, deleting stays with the owner. An own list is shared with „Teilen …“.
struct ListEntry: Identifiable {
    let id: String
    let text: String
    let qty: String
    /// „bis“ (from a meeting in the Begleiter): "bis Fr 24.10." / "due Fri 24 Oct", "" without; late: the day has passed
    let due: String
    let late: Bool
    let at: Date?
    let by: String
    let src: String
    let dept: String
    let done: Date?
    let doneBy: String

    init(_ d: [String: Any], en: Bool) {
        id = d["id"] as? String ?? ""
        text = d["text"] as? String ?? ""
        qty = d["qty"] as? String ?? ""
        let raw = d["due"] as? String ?? ""
        let f0 = DateFormatter()
        f0.calendar = Calendar(identifier: .gregorian)
        f0.locale = Locale(identifier: "en_US_POSIX")
        f0.dateFormat = "yyyy-MM-dd"
        if raw.count == 10, let day = f0.date(from: raw) {
            let f1 = DateFormatter()
            f1.locale = Locale(identifier: en ? "en_GB" : "de_DE")
            f1.dateFormat = en ? "EEE d MMM" : "EEE dd.MM."
            due = (en ? "due " : "bis ") + f1.string(from: day)
            late = raw < f0.string(from: Date())
        } else {
            due = ""
            late = false
        }
        let t = (d["t"] as? NSNumber)?.doubleValue ?? 0
        at = t > 0 ? Date(timeIntervalSince1970: t) : nil
        by = d["by_name"] as? String ?? ""
        src = d["src"] as? String ?? ""
        dept = (en ? d["dept_en"] : d["dept"]) as? String ?? ""
        let f = (d["done"] as? NSNumber)?.doubleValue ?? 0
        done = f > 0 ? Date(timeIntervalSince1970: f) : nil
        doneBy = d["done_name"] as? String ?? ""
    }
}

struct SparkListe: Identifiable {
    let id: String
    let name: String
    let icon: String
    let own: Bool
    let shop: Bool
    let onCalendar: Bool
    let error: String
    let items: [ListEntry]
    let done: [ListEntry]
    /// shared with this profile: whose list it is and „see“ or „add“; empty for an own list
    let owner: String
    let level: String
    /// an own list: profile id → „see“ or „add“
    let shares: [String: String]

    var mine: Bool { level.isEmpty }
    var write: Bool { level != "see" }
}

/// a profile an own list can be shared with (names only, from the Spark)
struct ListPerson: Identifiable {
    let id: String
    let name: String
}

@MainActor
final class ListenModel: ObservableObject {
    @Published var lists: [SparkListe] = []
    @Published var icons: [String] = []
    @Published var loading = true
    @Published var error: String?
    /// Listen teilen is released by the admin; the other profiles and the profile's note setting
    @Published var sharing = false
    @Published var people: [ListPerson] = []
    @Published var note = true
    /// Mitschreib-Link is released by the admin (mitschreiblink.py)
    @Published var linking = false
    private var sources: [String: [String]] = [:]
    static let en = Locale.current.language.languageCode?.identifier != "de"

    func list(_ id: String) -> SparkListe? { lists.first { $0.id == id } }

    /// where an entry came from, in the app's language („Stimme“, „Telegram“, …)
    func source(_ k: String) -> String { (sources[k] ?? []).dropFirst(Self.en ? 1 : 0).first ?? "" }

    private func take(_ d: [String: Any]) {
        let all = d["lists"] as? [String: [String: Any]] ?? [:]
        lists = (d["order"] as? [String] ?? []).compactMap { (k: String) -> SparkListe? in
            guard let l = all[k] else { return nil }
            let en = Self.en && !(l["own"] as? Bool ?? false)
            let sh = l["shared"] as? [String: Any] ?? [:]
            return SparkListe(id: k, name: (en ? l["name_en"] : l["name"]) as? String ?? k, icon: l["icon"] as? String ?? "",
                             own: l["own"] as? Bool ?? false, shop: l["shop"] as? Bool ?? false, onCalendar: l["target"] is [String: Any],
                             error: l["error"] as? String ?? "",
                             items: (l["items"] as? [[String: Any]] ?? []).map { ListEntry($0, en: Self.en) },
                             done: (l["done"] as? [[String: Any]] ?? []).map { ListEntry($0, en: Self.en) },
                             owner: sh["owner"] as? String ?? "", level: sh["level"] as? String ?? "",
                             shares: l["shares"] as? [String: String] ?? [:])
        }
        sharing = d["sharing"] as? Bool ?? false
        linking = d["linking"] as? Bool ?? false
        people = (d["people"] as? [[String: Any]] ?? []).map { ListPerson(id: $0["id"] as? String ?? "", name: $0["name"] as? String ?? "") }
        note = d["note"] as? Bool ?? note
        icons = d["icons"] as? [String] ?? icons
        sources = d["sources"] as? [String: [String]] ?? sources
    }

    func load() async { await send("GET", "/api/profile/tasks") }

    /// the note when others put something on a shared list (the profile's own setting, the same as in the panel)
    func setNote(_ on: Bool) async {
        do {
            _ = try await SparkAPI.current?.call("PUT", "api/iphone/settings", body: ["list_note": on])
            note = on
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// one change; the Spark answers with all lists as they are now. true when it went through.
    @discardableResult
    func send(_ method: String, _ path: String, _ body: [String: Any]? = nil) async -> Bool {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); loading = false; return false }
        do {
            take(try await api.object(method, path, body: body))
            if method != "GET" { WidgetCenter.shared.reloadTimelines(ofKind: "spark.einkauf") }   // the Einkauf widget
            error = nil
            loading = false
            return true
        } catch {
            self.error = error.localizedDescription
            loading = false
            return false
        }
    }
}

struct ListenView: View {
    @StateObject private var m = ListenModel()
    @State private var making = false
    @State private var name = ""

    var body: some View {
        List {
            let shared = m.lists.filter { !$0.mine }
            if shared.isEmpty {
                ForEach(m.lists) { row($0) }
            } else {
                Section("Meine Listen") { ForEach(m.lists.filter(\.mine)) { row($0) } }
                Section("Mit mir geteilt") { ForEach(shared) { row($0) } }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Listen")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { name = ""; making = true } label: { Image(systemName: "plus") }.accessibilityLabel("Neue Liste")
            }
        }
        .alert("Neue Liste", isPresented: $making) {
            TextField("Name", text: $name)
            Button("Anlegen") { Task { await m.send("POST", "/api/profile/listen", ["name": name, "icon": m.icons.first ?? ""]) } }
            Button("Abbrechen", role: .cancel) {}
        }
        .refreshable { await m.load() }
        .task { await m.load() }
        .overlay { if m.loading && m.lists.isEmpty { LadeZeilen(rows: 4).padding() } }
    }

    private func row(_ l: SparkListe) -> some View {
        NavigationLink { ListeView(m: m, id: l.id) } label: {
            HStack {
                Text(verbatim: l.icon).frame(width: 28)
                VStack(alignment: .leading) {
                    Text(verbatim: l.name)
                    if !l.owner.isEmpty {
                        Text("von \(l.owner)").font(.caption).foregroundStyle(.secondary)
                    } else if !l.shares.isEmpty {
                        Text("Geteilt mit \(l.shares.count)").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Text(verbatim: "\(l.items.count)").foregroundStyle(.secondary)
            }
        }
    }
}

/// One list: add, tick off with a tap, delete with a swipe, „Zuletzt erledigt“ with „Zurückholen“; an own list can be
/// renamed or deleted.
struct ListeView: View {
    @ObservedObject var m: ListenModel
    let id: String
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var renaming = false
    @State private var newName = ""
    @State private var dropping = false
    @State private var sharingSheet = false
    @FocusState private var typing: Bool

    private var path: String { "/api/profile/tasks/" + id }

    var body: some View {
        let l = m.list(id)
        let teilen = (m.sharing || m.linking) && l?.mine == true && l?.onCalendar == false
        List {
            if let l, !l.mine {
                (l.write ? Text("Von \(l.owner) geteilt: du kannst eintragen und abhaken.") : Text("Von \(l.owner) geteilt: nur zum Ansehen."))
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if l?.write ?? true {
                Section {
                    HStack {
                        TextField("Eintragen, z. B. Milch 2x", text: $text).focused($typing).submitLabel(.done).onSubmit(add)
                        Button(action: add) { Image(systemName: "plus.circle.fill") }.disabled(text.isEmpty).accessibilityLabel("Eintragen")
                    }
                }
            }
            if let l {
                if l.items.isEmpty { Text("Die Liste ist leer.").foregroundStyle(.secondary) }
                ForEach(groups(l), id: \.0) { dept, rows in
                    Section {
                        ForEach(rows) { x in entry(x, l) }
                    } header: { if !dept.isEmpty { Text(verbatim: dept) } }
                }
                if !l.done.isEmpty {
                    Section("Zuletzt erledigt") {
                        ForEach(l.done) { x in
                            HStack {
                                Image(systemName: "checkmark.circle.fill").foregroundStyle(.secondary)
                                VStack(alignment: .leading) {
                                    Text(verbatim: line(x)).strikethrough().foregroundStyle(.secondary)
                                    Text(verbatim: who(x.doneBy, x.done, "")).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if l.write {
                                    Button("Zurückholen") { Task { await m.send("POST", path + "/undo", ["ids": [x.id]]) } }
                                        .buttonStyle(.borderless)
                                }
                            }
                            .swipeActions {
                                if l.mine {
                                    Button("Löschen", role: .destructive) { Task { await m.send("DELETE", path + "/" + x.id) } }
                                }
                            }
                        }
                    }
                }
                if !l.error.isEmpty { Text(verbatim: l.error).foregroundStyle(.red) }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(Text(verbatim: l.map { $0.icon + " " + $0.name } ?? ""))
        .toolbar {
            if l?.own == true || teilen {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        if teilen { Button("Teilen …") { sharingSheet = true } }
                        if l?.own == true {
                            Button("Umbenennen") { newName = l?.name ?? ""; renaming = true }
                            Button("Liste löschen", role: .destructive) { dropping = true }
                        }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
        }
        .sheet(isPresented: $sharingSheet) { NavigationStack { ListeTeilenView(m: m, id: id) } }
        .alert("Umbenennen", isPresented: $renaming) {
            TextField("Name", text: $newName)
            Button("Sichern") { Task { await m.send("PUT", "/api/profile/listen/" + id, ["name": newName]) } }
            Button("Abbrechen", role: .cancel) {}
        }
        .confirmationDialog("Die Liste mit allen Einträgen löschen?", isPresented: $dropping, titleVisibility: .visible) {
            Button("Liste löschen", role: .destructive) {
                Task { if await m.send("DELETE", "/api/profile/listen/" + id) { dismiss() } }
            }
        }
        .refreshable { await m.load() }
    }

    private func add() {
        let t = text.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        text = ""
        Task { await m.send("POST", path + "/add", ["text": t]) }
        typing = true
    }

    /// a shopping list by departments in the Spark's order, any other list as it is
    private func groups(_ l: SparkListe) -> [(String, [ListEntry])] {
        guard l.shop else { return l.items.isEmpty ? [] : [("", l.items)] }
        var order: [String] = []
        var by: [String: [ListEntry]] = [:]
        for x in l.items {
            if by[x.dept] == nil { order.append(x.dept) }
            by[x.dept, default: []].append(x)
        }
        return order.map { ($0, by[$0] ?? []) }
    }

    private func line(_ x: ListEntry) -> String { x.qty.isEmpty ? x.text : x.text + " · " + x.qty }

    private func who(_ name: String, _ at: Date?, _ src: String) -> String {
        [name, at.map { $0.formatted(.relative(presentation: .named)) } ?? "", m.source(src)]
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func entry(_ x: ListEntry, _ l: SparkListe) -> some View {
        Button {
            guard l.write else { return }
            Task { await m.send("POST", path + "/done", ["ids": [x.id]]) }
        } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "circle").foregroundStyle(l.write ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: line(x)).foregroundStyle(.primary)
                    if !x.due.isEmpty {
                        Text(verbatim: x.due).font(.caption.weight(.semibold))
                            .foregroundStyle(x.late ? AnyShapeStyle(.red) : AnyShapeStyle(.tint))
                    }
                    let w = who(x.by, x.at, x.src)
                    if !w.isEmpty { Text(verbatim: w).font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
        .accessibilityHint(l.write ? Text("Abhaken") : Text(verbatim: ""))
        .swipeActions {
            if !l.onCalendar && l.mine {
                Button("Löschen", role: .destructive) { Task { await m.send("DELETE", path + "/" + x.id) } }
            }
        }
    }
}

/// „Teilen …“ for an own list: per profile Aus, Sehen or Mitschreiben, and the profile's note on new entries from others.
struct ListeTeilenView: View {
    @ObservedObject var m: ListenModel
    let id: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let l = m.list(id)
        Form {
            if m.sharing { people(l) }
            if m.linking { ListeLinkSection(id: id) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(Text(verbatim: l.map { $0.icon + " " + $0.name } ?? ""))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
    }

    @ViewBuilder private func people(_ l: SparkListe?) -> some View {
        Section {
            if m.people.isEmpty { Text("Es gibt keine anderen Profile.").foregroundStyle(.secondary) }
            ForEach(m.people) { p in
                Picker(selection: Binding(get: { l?.shares[p.id] ?? "" }, set: { v in
                    Task { await m.send("PUT", "/api/profile/listen/" + id + "/share", ["to": p.id, "level": v]) }
                })) {
                    Text("Aus").tag("")
                    Text("Sehen").tag("see")
                    Text("Mitschreiben").tag("add")
                } label: { Text(verbatim: p.name) }
            }
        } footer: {
            Text("Mitschreiben heißt eintragen und abhaken. Löschen und Teilen bleiben bei dir.")
        }
        Section {
            Toggle("Hinweis bei neuen Einträgen", isOn: Binding(get: { m.note }, set: { v in Task { await m.setNote(v) } }))
        } footer: {
            Text("Höchstens alle 10 Minuten ein Hinweis, wenn andere etwas auf eine geteilte Liste setzen.")
        }
    }
}

/// Mitschreib-Link (mitschreiblink.py): a link for people without a profile, put on only (optionally see).
/// The Spark never shows a link again; the app shows the new one once, with its QR code, to pass on.
struct ListeLinkSection: View {
    let id: String
    @State private var links: [[String: Any]] = []
    @State private var days = 30
    @State private var see = false
    @State private var made: String?
    @State private var error: String?

    private var path: String { "/api/profile/listen/" + id + "/links" }

    var body: some View {
        Section {
            ForEach(links.indices, id: \.self) { i in
                let x = links[i]
                HStack {
                    VStack(alignment: .leading) {
                        Text("Link bis \(Date(timeIntervalSince1970: x["until"] as? Double ?? 0).formatted(date: .abbreviated, time: .omitted))")
                        Text((x["see"] as? Bool ?? false) ? "eintragen und ansehen" : "nur eintragen").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Widerrufen", role: .destructive) { Task { await call("DELETE", path + "/" + (x["id"] as? String ?? "")) } }
                        .buttonStyle(.borderless)
                }
            }
            if let made, let url = URL(string: made) {
                if let qr = Self.qr(made) {
                    Image(uiImage: qr).interpolation(.none).resizable().scaledToFit().frame(maxWidth: 200).frame(maxWidth: .infinity)
                }
                ShareLink(item: url) { Label("Link weitergeben", systemImage: "square.and.arrow.up") }
                Text("Nur jetzt sichtbar: weitergeben oder den QR-Code zeigen.").font(.caption).foregroundStyle(.secondary)
            }
            Picker("Gültig für", selection: $days) {
                Text("7 Tage").tag(7)
                Text("30 Tage").tag(30)
                Text("1 Jahr").tag(365)
            }
            Toggle("darf die Liste sehen", isOn: $see)
            Button("Link erstellen") { Task { await call("POST", path, ["days": days, "see": see, "base": Self.base()]) } }
            if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
        } header: {
            Text("Link für Leute ohne Profil")
        } footer: {
            Text("Wer den Link hat, setzt nur etwas auf diese Liste: kein Abhaken, kein Löschen, kein Assistent.")
        }
        .task { await call("GET", path) }
    }

    /// the panel's address without a path: the link is <base>/#liste=<code>
    static func base() -> String {
        guard let b = SparkAPI.current?.base, let c = URLComponents(url: b, resolvingAgainstBaseURL: false),
              let scheme = c.scheme, let host = c.host else { return "" }
        return scheme + "://" + host + (c.port.map { ":\($0)" } ?? "")
    }

    static func qr(_ text: String) -> UIImage? {
        let f = CIFilter.qrCodeGenerator()
        f.message = Data(text.utf8)
        guard let out = f.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)),
              let cg = CIContext().createCGImage(out, from: out.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    private func call(_ method: String, _ p: String, _ body: [String: Any]? = nil) async {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); return }
        do {
            let d = try await api.object(method, p, body: body)
            links = d["links"] as? [[String: Any]] ?? []
            if method == "POST" { made = d["link"] as? String }
            if method == "DELETE" { made = nil }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
