import SwiftUI
import WidgetKit
import CoreImage.CIFilterBuiltins

/// Listen (plan listen-teilen.md, Dominik 2026-10-20 „1a 2a“): the same lists as the panel's page Listen (tasks.py):
/// Einkauf, Aufgaben and own lists, who put an entry on and from where, „Erledigt“ with „Zurückholen“, the shopping
/// list by departments. Opens with the admin's release of Listen (iphone.THINGS "tasks"); every rule stays on the Spark.
/// Listen teilen (Stufe 2): lists other profiles share show under „Mit mir geteilt“ with whose they are; „Sehen“ only
/// shows them, „Mitschreiben“ adds and ticks off, deleting stays with the owner. An own list is shared with „Teilen …“.
/// Apple-Stil Stufe 4 (plan apple-stil/plan.md „7a“): like Apple's Reminders. Tiles Heute, Geplant, Alle, Markiert
/// (counted here from the entries), lists with their colour, „Neue Erinnerung“ as the last row, ⓘ per entry (note,
/// date, time with „Erinnern“, flag, priority, list), drag to sort. The colours come from Theme.list.
struct ListEntry: Identifiable {
    let id: String
    let text: String
    let qty: String
    /// „bis“ (from a meeting in the Begleiter): "bis Fr 24.10." / "due Fri 24 Oct", "" without; late: the day has passed
    let due: String
    let late: Bool
    /// the raw date „JJJJ-MM-TT“ and time „HH:MM“ ("" without), note, flag, priority 0-3, „Erinnern“
    let dueDay: String
    let time: String
    let note: String
    let flag: Bool
    let prio: Int
    let remind: Bool
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
        dueDay = raw
        time = d["at"] as? String ?? ""
        note = d["note"] as? String ?? ""
        flag = d["flag"] as? Bool ?? false
        prio = (d["prio"] as? NSNumber)?.intValue ?? 0
        remind = d["remind"] as? Bool ?? false
        let f0 = DateFormatter()
        f0.calendar = Calendar(identifier: .gregorian)
        f0.locale = Locale(identifier: "en_US_POSIX")
        f0.dateFormat = "yyyy-MM-dd"
        if raw.count == 10, let day = f0.date(from: raw) {
            let f1 = DateFormatter()
            f1.locale = Locale(identifier: en ? "en_GB" : "de_DE")
            f1.dateFormat = en ? "EEE d MMM" : "EEE dd.MM."
            due = (en ? "due " : "bis ") + f1.string(from: day) + (time.isEmpty ? "" : ", " + time)
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
    /// the list's colour (tasks.COLORS) for Theme.list
    let color: String
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
    /// the colours a list can have and whether „Erinnern“ works (Timer und Erinnerungen is allowed)
    @Published var colors: [String] = []
    @Published var reminders = false
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
                             color: l["color"] as? String ?? "",
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
        colors = d["colors"] as? [String] ?? colors
        reminders = d["reminders"] as? Bool ?? false
        sources = d["sources"] as? [String: [String]] ?? sources
    }

    func load() async { await send("GET", "/api/profile/tasks") }

    /// today as „JJJJ-MM-TT“ (the tiles and Geplant)
    static func day(_ add: Int = 0) -> String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Calendar.current.date(byAdding: .day, value: add, to: Date()) ?? Date())
    }

    /// the open entries of every list with their list, for the tiles and the search
    func all() -> [(ListEntry, SparkListe)] { lists.flatMap { l in l.items.map { ($0, l) } } }

    /// whether an entry belongs to a tile: heute (due today or before), geplant (with a date), alle, markiert
    static func fits(_ kind: String, _ x: ListEntry) -> Bool {
        switch kind {
        case "heute": return !x.dueDay.isEmpty && x.dueDay <= day()
        case "geplant": return !x.dueDay.isEmpty
        case "markiert": return x.flag
        default: return true
        }
    }

    /// a colour's name in the app's language (tasks.COLORS are German words without umlauts)
    static func colorName(_ c: String) -> String {
        let names = ["blau": ("Blau", "Blue"), "rot": ("Rot", "Red"), "orange": ("Orange", "Orange"), "gelb": ("Gelb", "Yellow"),
                     "gruen": ("Grün", "Green"), "tuerkis": ("Türkis", "Teal"), "lila": ("Lila", "Purple"),
                     "rosa": ("Rosa", "Pink"), "braun": ("Braun", "Brown"), "grau": ("Grau", "Grey")]
        guard let n = names[c] else { return c }
        return en ? n.1 : n.0
    }

    /// the entry with this id on this list, as it is now
    func entry(_ list: String, _ id: String) -> ListEntry? { self.list(list)?.items.first { $0.id == id } }

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
    @State private var query = ""

    var body: some View {
        List {
            if !query.trimmingCharacters(in: .whitespaces).isEmpty {
                let q = query.lowercased()
                let hits = m.all().filter { ($0.0.text + " " + $0.0.note).lowercased().contains(q) }
                Section {
                    if hits.isEmpty { Text("Nichts gefunden.").foregroundStyle(.secondary) }
                    ForEach(hits, id: \.0.id) { x, l in
                        NavigationLink { ListeView(m: m, id: l.id) } label: {
                            VStack(alignment: .leading) {
                                Text(verbatim: x.text)
                                Text(verbatim: l.name).font(.caption).foregroundStyle(Theme.list(l.color))
                            }
                        }
                    }
                }
            } else {
                Section {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: Theme.s2), GridItem(.flexible(), spacing: Theme.s2)], spacing: Theme.s2) {
                        tile("heute", "calendar.badge.clock", "blau", "Heute")
                        tile("geplant", "calendar", "rot", "Geplant")
                        tile("alle", "tray", "grau", "Alle")
                        tile("markiert", "flag.fill", "orange", "Markiert")
                    }
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
                let shared = m.lists.filter { !$0.mine }
                Section("Meine Listen") {
                    ForEach(m.lists.filter(\.mine)) { row($0) }
                        .onMove { from, to in
                            var order = m.lists.map(\.id)
                            let mine = m.lists.filter(\.mine).map(\.id)
                            var moved = mine
                            moved.move(fromOffsets: from, toOffset: to)
                            order = moved + order.filter { !mine.contains($0) }
                            Task { await m.send("PUT", "/api/profile/listen/order", ["order": order]) }
                        }
                }
                if !shared.isEmpty { Section("Mit mir geteilt") { ForEach(shared) { row($0) } } }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
        }
        .searchable(text: $query, prompt: Text("Suchen"))
        .navigationTitle("Listen")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { name = ""; making = true } label: { Image(systemName: "plus") }.accessibilityLabel("Neue Liste")
            }
            ToolbarItem(placement: .secondaryAction) { EditButton() }
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

    /// one of the four tiles: its symbol on its colour, how many, its name
    private func tile(_ kind: String, _ symbol: String, _ color: String, _ title: LocalizedStringKey) -> some View {
        NavigationLink { SmartListeView(m: m, kind: kind, title: title, color: color) } label: {
            VStack(alignment: .leading, spacing: Theme.s1) {
                HStack {
                    Image(systemName: symbol).font(.footnote.weight(.semibold)).foregroundStyle(Theme.onAccent)
                        .frame(width: 28, height: 28).background(Circle().fill(Theme.list(color)))
                    Spacer()
                    Text(verbatim: "\(m.all().filter { ListenModel.fits(kind, $0.0) }.count)").font(.title2.bold())
                        .foregroundStyle(Theme.fg)
                }
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.muted)
            }
            .padding(Theme.s3)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: Theme.rBox).fill(Theme.card))
        }
        .buttonStyle(.plain)
    }

    private func row(_ l: SparkListe) -> some View {
        NavigationLink { ListeView(m: m, id: l.id) } label: {
            HStack {
                Text(verbatim: l.icon).frame(width: 30, height: 30).background(Circle().fill(Theme.list(l.color).opacity(0.22)))
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
    @State private var coloring = false
    @State private var info: String?
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
            if let l {
                ForEach(groups(l), id: \.0) { dept, rows in
                    Section {
                        ForEach(rows) { x in entry(x, l) }
                            .onMove(perform: mover(l, rows))
                    } header: { if !dept.isEmpty { Text(verbatim: dept) } }
                }
                // the empty row at the end: type, return, and the next one (several at once with commas)
                if l.write {
                    Section {
                        HStack {
                            Image(systemName: "circle.dashed").foregroundStyle(Theme.list(l.color))
                            TextField("Neue Erinnerung", text: $text).focused($typing).submitLabel(.next).onSubmit(add)
                        }
                    } footer: { Text("Mehrere mit Komma, z. B. „2 Milch, Brot“") }
                } else if l.items.isEmpty {
                    Text("Die Liste ist leer.").foregroundStyle(.secondary)
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
                if !l.error.isEmpty { Text(verbatim: l.error).foregroundStyle(Theme.badText) }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
        }
        .navigationTitle(Text(verbatim: l.map { $0.icon + " " + $0.name } ?? ""))
        .tint(Theme.list(l?.color ?? ""))
        .toolbar {
            if l?.mine == true {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        if teilen { Button("Teilen …") { sharingSheet = true } }
                        Button("Farbe …") { coloring = true }
                        if l?.own == true {
                            Button("Umbenennen") { newName = l?.name ?? ""; renaming = true }
                            Button("Liste löschen", role: .destructive) { dropping = true }
                        }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
            if l?.write == true && l?.shop == false && l?.onCalendar == false {
                ToolbarItem(placement: .secondaryAction) { EditButton() }
            }
        }
        .sheet(isPresented: $sharingSheet) { NavigationStack { ListeTeilenView(m: m, id: id) } }
        .sheet(item: Binding(get: { info.map { EintragRef(list: id, id: $0) } }, set: { info = $0?.id })) { r in
            NavigationStack { EintragInfoView(m: m, list: r.list, id: r.id) }
        }
        .confirmationDialog("Farbe", isPresented: $coloring) {
            ForEach(m.colors, id: \.self) { c in
                Button(ListenModel.colorName(c)) {
                    Task { await m.send("PUT", "/api/profile/listen/" + id, ["color": c]) }
                }
            }
        }
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

    /// dragging an entry to another place (Bearbeiten): the new order of the open entries; not on a shopping list
    /// (sorted by departments), a list shared to look at or a CalDAV list
    private func mover(_ l: SparkListe, _ rows: [ListEntry]) -> ((IndexSet, Int) -> Void)? {
        if l.shop || !l.write || l.onCalendar { return nil }
        let p = path
        let model = m
        return { from, to in
            var ids = rows.map(\.id)
            ids.move(fromOffsets: from, toOffset: to)
            Task { await model.send("PUT", p + "/order", ["ids": ids]) }
        }
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

    /// one entry: the round box ticks it off, ⓘ opens its info (no button inside another, so both get their tap)
    private func entry(_ x: ListEntry, _ l: SparkListe) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Button {
                guard l.write else { return }
                Task { await m.send("POST", path + "/done", ["ids": [x.id]]) }
            } label: {
                Image(systemName: "circle").foregroundStyle(l.write ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(l.write ? Text("Abhaken") : Text(verbatim: x.text))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: (x.prio > 0 ? String(repeating: "!", count: x.prio) + " " : "") + line(x)).foregroundStyle(.primary)
                if !x.due.isEmpty {
                    Text(verbatim: x.due).font(.caption.weight(.semibold))
                        .foregroundStyle(x.late ? AnyShapeStyle(Theme.bad) : AnyShapeStyle(.tint))
                }
                if !x.note.isEmpty { Text(verbatim: x.note).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                let w = who(x.by, x.at, x.src)
                if !w.isEmpty { Text(verbatim: w).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer()
            if x.flag { Image(systemName: "flag.fill").foregroundStyle(Theme.lstOrange).accessibilityLabel("Markiert") }
            if l.write && !l.onCalendar {
                Button { info = x.id } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.borderless).accessibilityLabel("Info")
            }
        }
        .swipeActions {
            if !l.onCalendar && l.mine {
                Button("Löschen", role: .destructive) { Task { await m.send("DELETE", path + "/" + x.id) } }
            }
        }
    }
}

/// which entry the info sheet shows
struct EintragRef: Identifiable {
    let list: String
    let id: String
}

/// One tile (Heute, Geplant, Alle, Markiert): the open entries of every list that fit, by list (Geplant: by day);
/// a tap ticks off, ⓘ opens the info, as on the list itself.
struct SmartListeView: View {
    @ObservedObject var m: ListenModel
    let kind: String
    let title: LocalizedStringKey
    let color: String
    @State private var info: EintragRef?

    var body: some View {
        let hits = m.all().filter { ListenModel.fits(kind, $0.0) }
        List {
            if hits.isEmpty { Text("Keine Einträge.").foregroundStyle(.secondary) }
            ForEach(groups(hits), id: \.0) { head, rows in
                Section {
                    ForEach(rows, id: \.0.id) { x, l in row(x, l) }
                } header: { Text(verbatim: head) }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
        }
        .navigationTitle(title)
        .tint(Theme.list(color))
        .refreshable { await m.load() }
        .sheet(item: $info) { r in NavigationStack { EintragInfoView(m: m, list: r.list, id: r.id) } }
    }

    private func groups(_ hits: [(ListEntry, SparkListe)]) -> [(String, [(ListEntry, SparkListe)])] {
        var order: [String] = []
        var by: [String: [(ListEntry, SparkListe)]] = [:]
        let sorted = kind == "geplant" ? hits.sorted { ($0.0.dueDay + $0.0.time) < ($1.0.dueDay + $1.0.time) } : hits
        for h in sorted {
            let k = kind == "geplant" ? (h.0.dueDay < ListenModel.day() ? String(localized: "Überfällig") : h.0.due) : h.1.name
            if by[k] == nil { order.append(k) }
            by[k, default: []].append(h)
        }
        return order.map { ($0, by[$0] ?? []) }
    }

    private func row(_ x: ListEntry, _ l: SparkListe) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Button {
                guard l.write else { return }
                Task { await m.send("POST", "/api/profile/tasks/" + l.id + "/done", ["ids": [x.id]]) }
            } label: { Image(systemName: "circle").foregroundStyle(Theme.list(l.color)) }
                .buttonStyle(.borderless).accessibilityLabel("Abhaken")
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: (x.prio > 0 ? String(repeating: "!", count: x.prio) + " " : "") + x.text)
                if !x.due.isEmpty {
                    Text(verbatim: x.due).font(.caption.weight(.semibold))
                        .foregroundStyle(x.late ? AnyShapeStyle(Theme.bad) : AnyShapeStyle(.tint))
                }
                Text(verbatim: l.name).font(.caption).foregroundStyle(Theme.list(l.color))
            }
            Spacer()
            if x.flag { Image(systemName: "flag.fill").foregroundStyle(Theme.lstOrange).accessibilityLabel("Markiert") }
            if l.write && !l.onCalendar {
                Button { info = EintragRef(list: l.id, id: x.id) } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.borderless).accessibilityLabel("Info")
            }
        }
    }
}

/// ⓘ of one entry: title, note, date, time with „Erinnern“, flag, priority and the list; every change goes to the
/// Spark at once (PUT …/<entry>), moving and deleting only on the owner's own list.
struct EintragInfoView: View {
    @ObservedObject var m: ListenModel
    let list: String
    let id: String
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var note = ""
    @State private var ready = false

    private var path: String { "/api/profile/tasks/" + list + "/" + id }

    var body: some View {
        let x = m.entry(list, id)
        let l = m.list(list)
        Form {
            if let x, let l {
                Section {
                    TextField("Titel", text: $title).onSubmit { save(["text": title]) }
                    TextField("Notiz", text: $note, axis: .vertical).lineLimit(2...6)
                }
                Section {
                    Toggle("Datum", isOn: Binding(get: { !x.dueDay.isEmpty }, set: { on in save(["due": on ? ListenModel.day() : ""]) }))
                    if !x.dueDay.isEmpty {
                        DatePicker("Datum", selection: Binding(get: { Self.date(x.dueDay, "") ?? Date() },
                                                                  set: { save(["due": Self.text($0, "yyyy-MM-dd")]) }),
                                   displayedComponents: .date)
                        Toggle("Uhrzeit", isOn: Binding(get: { !x.time.isEmpty }, set: { on in save(["at": on ? "09:00" : ""]) }))
                        if !x.time.isEmpty {
                            DatePicker("Uhrzeit", selection: Binding(get: { Self.date(x.dueDay, x.time) ?? Date() },
                                                                      set: { save(["at": Self.text($0, "HH:mm")]) }),
                                       displayedComponents: .hourAndMinute)
                            Toggle("Erinnern", isOn: Binding(get: { x.remind }, set: { save(["remind": $0]) })).disabled(!m.reminders)
                        }
                    }
                } footer: {
                    if !m.reminders { Text(SparkAPI.way(String(localized: "Erinnern braucht Funktionen → Timer und Erinnerungen."))) }
                }
                Section {
                    Toggle("Markiert", isOn: Binding(get: { x.flag }, set: { save(["flag": $0]) }))
                    Picker("Priorität", selection: Binding(get: { x.prio }, set: { save(["prio": $0]) })) {
                        Text("Keine").tag(0)
                        Text(verbatim: "!").tag(1)
                        Text(verbatim: "!!").tag(2)
                        Text(verbatim: "!!!").tag(3)
                    }
                    if l.mine {
                        Picker("Liste", selection: Binding(get: { list }, set: { to in
                            guard to != list else { return }
                            Task { if await m.send("PUT", path, ["to": to]) { dismiss() } }
                        })) {
                            ForEach(m.lists.filter { $0.id == list || ($0.write && !$0.onCalendar) }) { Text(verbatim: $0.name).tag($0.id) }
                        }
                    }
                }
                if l.mine {
                    Section {
                        Button("Löschen", role: .destructive) {
                            Task { if await m.send("DELETE", path) { dismiss() } }
                        }
                    }
                }
            } else {
                Text("Diesen Eintrag gibt es nicht mehr.").foregroundStyle(.secondary)
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
        }
        .navigationTitle("Info")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        .onDisappear {   // title and note go when the sheet closes, however it is closed
            guard ready, let x = m.entry(list, id) else { return }
            var ch: [String: Any] = [:]
            if title != x.text + (x.qty.isEmpty ? "" : " " + x.qty), !title.isEmpty { ch["text"] = title }
            if note != x.note { ch["note"] = note }
            if !ch.isEmpty { save(ch) }
        }
        .onAppear {
            guard !ready, let x = m.entry(list, id) else { return }
            title = x.text + (x.qty.isEmpty ? "" : " " + x.qty)
            note = x.note
            ready = true
        }
    }

    private func save(_ body: [String: Any]) { Task { await m.send("PUT", path, body) } }

    static func date(_ day: String, _ time: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = time.isEmpty ? "yyyy-MM-dd" : "yyyy-MM-dd HH:mm"
        return f.date(from: time.isEmpty ? day : day + " " + time)
    }

    static func text(_ d: Date, _ format: String) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = format
        return f.string(from: d)
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
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
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
            if let error { Text(SparkAPI.way(error)).foregroundStyle(Theme.badText) }
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
