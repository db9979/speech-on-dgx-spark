import SwiftUI

/// Kontakte (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): the same cards as the panel's page Kontakte (contacts.py):
/// A–Z with a search, the card with Nachricht, Anruf, Mail, Termin and Teilen and „Mit Anna“ (the next appointment and
/// the latest mail). Opens with the admin's release of Kontakte (iphone.THINGS "contacts"); „Bearbeiten“, „Neuer
/// Kontakt“ and „Kontakt löschen“ only with Kontakte ändern ("kontakteaendern"). The Spark checks every field again and
/// writes the card back into its own address book with its ETag; changed meanwhile → nothing is overwritten.
struct SparkKontakt: Identifiable, Hashable {
    let id: String
    let etag: String
    let edit: Bool
    let name: String
    let given: String
    let family: String
    let nick: String
    let org: String
    let title: String
    let phones: [[String]]
    let emails: [String]
    let addrs: [[String: String]]
    let urls: [String]
    let bday: String
    let note: String
    let book: String

    init(_ d: [String: Any]) {
        id = d["id"] as? String ?? ""
        etag = d["etag"] as? String ?? ""
        edit = d["edit"] as? Bool ?? false
        name = d["name"] as? String ?? ""
        given = d["given"] as? String ?? ""
        family = d["family"] as? String ?? ""
        nick = d["nick"] as? String ?? ""
        org = d["org"] as? String ?? ""
        title = d["title"] as? String ?? ""
        phones = d["phones"] as? [[String]] ?? []
        emails = d["emails"] as? [String] ?? []
        addrs = d["addrs"] as? [[String: String]] ?? []
        urls = d["urls"] as? [String] ?? []
        bday = d["bday"] as? String ?? ""
        note = d["note"] as? String ?? ""
        book = d["book"] as? String ?? ""
    }

    /// the letter it stands under: the family name (or name) without accents, „#“ for anything else
    var letter: String {
        let s = (family.isEmpty ? name : family).folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
        let c = s.prefix(1).uppercased()
        return c.range(of: "^[A-Z]$", options: .regularExpression) != nil ? c : "#"
    }

    var initials: String {
        let s = String((given.isEmpty ? name : given).prefix(1)) + String(family.prefix(1))
        return s.isEmpty ? "?" : s.uppercased()
    }
}

struct KontaktBuch: Identifiable, Hashable {
    let id: String
    let name: String
}

/// the labels of the page (kontaktkarte.PHONE_KINDS, ADDR_KINDS); the Spark keeps the German word, the app shows it
enum KontaktArt {
    static let phone = ["Handy", "Privat", "Arbeit", "Telefon"]
    static let addr = ["Privat", "Arbeit", "Adresse"]
    static func label(_ k: String) -> String {
        switch k {
        case "Handy": return String(localized: "Handy")
        case "Privat": return String(localized: "Privat")
        case "Arbeit": return String(localized: "Arbeit")
        case "Adresse": return String(localized: "Adresse")
        default: return String(localized: "Telefon")
        }
    }
}

@MainActor
final class KontakteModel: ObservableObject {
    @Published var cards: [SparkKontakt] = []
    @Published var books: [KontaktBuch] = []
    @Published var edit = false
    @Published var loading = true
    @Published var error: String?

    func card(_ id: String) -> SparkKontakt? { cards.first { $0.id == id } }
    func book(_ id: String) -> String { books.first { $0.id == id }?.name ?? "" }

    func load() async {
        guard let api = SparkAPI.current else { error = String(localized: "Nicht gekoppelt."); loading = false; return }
        do {
            let d = try await api.object("GET", "/api/profile/contacts/page")
            cards = (d["cards"] as? [[String: Any]] ?? []).map(SparkKontakt.init)
            books = (d["books"] as? [[String: Any]] ?? []).map { KontaktBuch(id: $0["id"] as? String ?? "", name: $0["name"] as? String ?? "") }
            edit = d["edit"] as? Bool ?? false
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// a new card (id nil) or a change; returns the card as the Spark keeps it, nil with the reason in error
    func save(_ id: String?, _ body: [String: Any]) async -> SparkKontakt? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object(id == nil ? "POST" : "PUT", "/api/profile/contacts/card" + (id.map { "/" + $0 } ?? ""), body: body)
            let c = SparkKontakt(d)
            cards.removeAll { $0.id == c.id }
            cards.append(c)
            cards.sort { ($0.family.isEmpty ? $0.name : $0.family).lowercased() < ($1.family.isEmpty ? $1.name : $1.family).lowercased() }
            error = nil
            return c
        } catch {
            self.error = error.localizedDescription
            await load()   // changed meanwhile: the card as it is now
            return nil
        }
    }

    func delete(_ c: SparkKontakt) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            _ = try await api.call("DELETE", "/api/profile/contacts/card/" + c.id, query: ["etag": c.etag])
            cards.removeAll { $0.id == c.id }
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            await load()
            return false
        }
    }
}

struct KontakteView: View {
    @StateObject private var m = KontakteModel()
    @State private var search = ""
    @State private var making: KontaktEntwurf?

    private var shown: [SparkKontakt] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return m.cards }
        return m.cards.filter { c in
            ([c.name, c.org, c.nick] + c.emails + c.phones.compactMap { $0.last }).contains { $0.lowercased().contains(q) }
        }
    }

    var body: some View {
        let groups = Dictionary(grouping: shown, by: \.letter)
        let letters = groups.keys.sorted { $0 == "#" ? false : $1 == "#" ? true : $0 < $1 }
        ScrollViewReader { proxy in
            List {
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
                if !m.loading && m.cards.isEmpty {
                    Text(SparkAPI.way(String(localized: "Noch keine Kontakte. Ein Adressbuch kommt im Browser unter Kontakte → Einstellungen dazu."))).foregroundStyle(.secondary)
                }
                ForEach(letters, id: \.self) { l in
                    Section {
                        ForEach(groups[l] ?? []) { c in
                            NavigationLink { KontaktDetail(m: m, id: c.id) } label: { row(c) }
                        }
                    } header: { Text(verbatim: l) }
                    .id(l)
                }
            }
            .overlay(alignment: .trailing) {
                if letters.count > 1 && search.isEmpty {
                    VStack(spacing: 1) {
                        ForEach(letters, id: \.self) { l in
                            Button { proxy.scrollTo(l, anchor: .top) } label: { Text(verbatim: l).font(.caption2.bold()) }
                        }
                    }
                    .padding(.trailing, 2)
                }
            }
        }
        .searchable(text: $search)
        .navigationTitle("Kontakte")
        .toolbar {
            if m.edit {
                ToolbarItem(placement: .primaryAction) {
                    Button { making = KontaktEntwurf(nil, books: m.books) } label: { Image(systemName: "plus") }.accessibilityLabel("Neuer Kontakt")
                }
            }
        }
        .sheet(item: $making) { e in KontaktForm(m: m, draft: e) }
        .refreshable { await m.load() }
        .task { await m.load() }
        .overlay { if m.loading && m.cards.isEmpty { LadeZeilen(rows: 6).padding() } }
    }

    private func row(_ c: SparkKontakt) -> some View {
        HStack {
            Text(verbatim: c.initials).font(.footnote.bold()).frame(width: 34, height: 34).background(Circle().fill(Color.secondary.opacity(0.2)))
            VStack(alignment: .leading) {
                Text(verbatim: c.name)
                if !c.org.isEmpty && c.org != c.name { Text(verbatim: c.org).font(.caption).foregroundStyle(.secondary) }
            }
        }
    }
}

/// One card as Apple Kontakte shows it: the round initials, the five buttons, the fields, „Mit Anna“.
struct KontaktDetail: View {
    @ObservedObject var m: KontakteModel
    let id: String
    @ObservedObject private var talk = Conversation.shared
    @Environment(\.openURL) private var openURL
    @State private var with: [String: Any] = [:]
    @State private var editing: KontaktEntwurf?
    @State private var writing: MailDraft?
    @State private var meeting = false
    @State private var file: URL?

    var body: some View {
        if let c = m.card(id) {
            List {
                Section {
                    VStack(spacing: 8) {
                        Text(verbatim: c.initials).font(.title.bold()).frame(width: 76, height: 76).background(Circle().fill(Color.secondary.opacity(0.2)))
                        Text(verbatim: c.name).font(.title2.bold()).multilineTextAlignment(.center)
                        let sub = [c.title, c.org == c.name ? "" : c.org].filter { !$0.isEmpty }.joined(separator: " · ")
                        if !sub.isEmpty { Text(verbatim: sub).foregroundStyle(.secondary) }
                        HStack(spacing: 8) {
                            knopf("Nachricht", "message.fill", tel(c).map { "sms:" + $0 })
                            knopf("Anruf", "phone.fill", tel(c).map { "tel:" + $0 })
                            Button { mail(c.emails.first ?? "") } label: { knopfBild("Mail", "envelope.fill") }
                                .disabled(c.emails.isEmpty)
                            Button { meeting = true } label: { knopfBild("Termin", "calendar") }
                                .disabled(!talk.allowed.areas.contains("calendar"))
                            if let file {
                                ShareLink(item: file) { knopfBild("Teilen", "square.and.arrow.up") }
                            }
                        }
                        .buttonStyle(.borderless)
                    }
                    .frame(maxWidth: .infinity)
                }
                .listRowBackground(Color.clear)
                if !c.phones.isEmpty {
                    Section {
                        ForEach(Array(c.phones.enumerated()), id: \.offset) { _, p in
                            if let num = p.last {
                                Button { if let u = URL(string: "tel:" + Self.digits(num)) { openURL(u) } } label: {
                                    LabeledContent(KontaktArt.label(p.first ?? ""), value: num)
                                }
                            }
                        }
                    }
                }
                if !c.emails.isEmpty {
                    Section {
                        ForEach(c.emails, id: \.self) { a in
                            Button { mail(a) } label: { LabeledContent("E-Mail", value: a) }
                        }
                    }
                }
                ForEach(Array(c.addrs.enumerated()), id: \.offset) { _, a in
                    Section {
                        LabeledContent(KontaktArt.label(a["kind"] ?? ""), value: [a["street"] ?? "", [a["zip"] ?? "", a["city"] ?? ""].filter { !$0.isEmpty }.joined(separator: " "),
                                                                                a["country"] ?? ""].filter { !$0.isEmpty }.joined(separator: "\n"))
                    }
                }
                if !c.urls.isEmpty || !c.bday.isEmpty || !c.nick.isEmpty || !c.note.isEmpty {
                    Section {
                        ForEach(c.urls, id: \.self) { u in
                            if let url = URL(string: u), ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                                Link(destination: url) { LabeledContent("Webseite", value: u) }
                            }
                        }
                        if !c.bday.isEmpty { LabeledContent("Geburtstag", value: Self.birthday(c.bday)) }
                        if !c.nick.isEmpty { LabeledContent("Spitzname", value: c.nick) }
                        if !c.note.isEmpty { LabeledContent("Notiz", value: c.note) }
                    }
                }
                if let ev = with["event"] as? [String: Any] {
                    Section(header: Text("Mit \(c.given.isEmpty ? c.name : c.given)")) {
                        LabeledContent("Nächster Termin", value: (ev["title"] as? String ?? "") + " · " + Self.when(ev["start"], day: ev["allday"] as? Bool ?? false))
                        if let ml = with["mail"] as? [String: Any] {
                            LabeledContent("Letzte Mail", value: (ml["subject"] as? String ?? "") + " · " + Self.when(ml["date"], day: true))
                        }
                    }
                } else if let ml = with["mail"] as? [String: Any] {
                    Section(header: Text("Mit \(c.given.isEmpty ? c.name : c.given)")) {
                        LabeledContent("Letzte Mail", value: (ml["subject"] as? String ?? "") + " · " + Self.when(ml["date"], day: true))
                    }
                }
                Section {
                    LabeledContent("Adressbuch", value: m.book(c.book))
                }
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .navigationTitle(Text(verbatim: c.name))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if c.edit && m.edit {
                    ToolbarItem(placement: .primaryAction) { Button("Bearbeiten") { editing = KontaktEntwurf(c, books: m.books) } }
                }
            }
            .sheet(item: $editing) { e in KontaktForm(m: m, draft: e) }
            .sheet(item: $writing) { d in MailWrite(draft: d) }
            .sheet(isPresented: $meeting) {
                NavigationStack { List { Section("Termin") { QuickAdd(text: String(localized: "Termin mit \(c.name) ")) { _, _ in meeting = false } } } }
            }
            .task(id: c.id) { await load(c) }
            .onDisappear { if let file { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) } }
        } else {
            Text("Der Kontakt ist nicht mehr da.").foregroundStyle(.secondary)
        }
    }

    private func tel(_ c: SparkKontakt) -> String? {
        let p = c.phones.first { $0.first == "Handy" } ?? c.phones.first
        return p?.last.map(Self.digits)
    }

    static func digits(_ s: String) -> String { s.filter { $0.isNumber || $0 == "+" } }

    /// Mail in the app's own form when the profile may send, otherwise the iPhone's mail program
    private func mail(_ a: String) {
        guard !a.isEmpty else { return }
        if talk.allowed.areas.contains("mailsend") {
            writing = MailDraft(to: a)
        } else if let u = URL(string: "mailto:" + a) {
            openURL(u)
        }
    }

    private func knopf(_ label: LocalizedStringKey, _ icon: String, _ href: String?) -> some View {
        Button { if let h = href, let u = URL(string: h) { openURL(u) } } label: { knopfBild(label, icon) }.disabled(href == nil)
    }

    private func knopfBild(_ label: LocalizedStringKey, _ icon: String) -> some View {
        VStack(spacing: 3) {
            Image(systemName: icon).font(.title3)
            Text(label).font(.caption2)
        }
        .frame(width: 58, height: 52)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.accentColor.opacity(0.12)))
    }

    static func birthday(_ s: String) -> String {
        let p = s.split(separator: "-", omittingEmptySubsequences: false).map(String.init)
        guard p.count == 3, let mo = Int(p[1]), let d = Int(p[2]),
              let day = Calendar(identifier: .gregorian).date(from: DateComponents(year: 2000, month: mo, day: d)) else { return s }
        return day.formatted(.dateTime.day().month(.wide)) + (p[0].isEmpty ? "" : " " + p[0])
    }

    static func when(_ t: Any?, day: Bool) -> String {
        let s = (t as? NSNumber)?.doubleValue ?? 0
        guard s > 0 else { return "" }
        let d = Date(timeIntervalSince1970: s)
        return day ? d.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated))
            : d.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute())
    }

    /// „Mit Anna“ and the card as a .vcf file for „Teilen“
    private func load(_ c: SparkKontakt) async {
        guard let api = SparkAPI.current else { return }
        if let d = try? await api.object("GET", "/api/profile/contacts/with/" + c.id, query: ["tz": TimeZone.current.identifier]) { with = d }
        if let data = try? await api.call("GET", "/api/profile/contacts/vcf/" + c.id) {
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let safe = c.name.filter { $0.isLetter || $0.isNumber || $0 == " " }
            let url = dir.appendingPathComponent((safe.isEmpty ? "Kontakt" : safe) + ".vcf")
            if (try? data.write(to: url)) != nil { file = url }
        }
    }
}

/// A row of the form: its kind and its value (an address keeps its four parts)
struct KontaktZeile: Identifiable {
    let id = UUID()
    var kind: String
    var value = ""
    var street = ""
    var zip = ""
    var city = ""
    var country = ""
}

struct KontaktEntwurf: Identifiable {
    let id = UUID()
    let card: String?
    let etag: String
    var book: String
    var given = ""
    var family = ""
    var org = ""
    var title = ""
    var nick = ""
    var phones: [KontaktZeile] = []
    var emails: [KontaktZeile] = []
    var addrs: [KontaktZeile] = []
    var urls: [KontaktZeile] = []
    var bday = ""
    var note = ""

    init(_ c: SparkKontakt?, books: [KontaktBuch]) {
        card = c?.id
        etag = c?.etag ?? ""
        book = c?.book ?? (books.first { $0.id != "spark" } ?? books.first)?.id ?? "spark"
        guard let c else { phones = [KontaktZeile(kind: "Handy")]; return }
        given = c.given; family = c.family; org = c.org; title = c.title; nick = c.nick; bday = c.bday; note = c.note
        phones = c.phones.map { KontaktZeile(kind: KontaktArt.phone.contains($0.first ?? "") ? $0.first ?? "Telefon" : "Telefon", value: $0.last ?? "") }
        emails = c.emails.map { KontaktZeile(kind: "", value: $0) }
        urls = c.urls.map { KontaktZeile(kind: "", value: $0) }
        addrs = c.addrs.map { KontaktZeile(kind: $0["kind"] ?? "Adresse", street: $0["street"] ?? "", zip: $0["zip"] ?? "", city: $0["city"] ?? "", country: $0["country"] ?? "") }
    }

    var body: [String: Any] {
        ["book": book, "etag": etag, "given": given, "family": family, "org": org, "title": title, "nick": nick, "bday": bday, "note": note,
         "phones": phones.filter { !$0.value.isEmpty }.map { [$0.kind, $0.value] },
         "emails": emails.map(\.value).filter { !$0.isEmpty }, "urls": urls.map(\.value).filter { !$0.isEmpty },
         "addrs": addrs.map { ["kind": $0.kind, "street": $0.street, "zip": $0.zip, "city": $0.city, "country": $0.country] }]
    }
}

/// „Bearbeiten“ like Apple: swipe or − removes a field, „hinzufügen“ adds one, „Fertig“ saves
struct KontaktForm: View {
    @ObservedObject var m: KontakteModel
    @State var draft: KontaktEntwurf
    @Environment(\.dismiss) private var dismiss
    @State private var busy = false
    @State private var asking = false
    @State private var error: String?

    init(m: KontakteModel, draft: KontaktEntwurf) {
        self.m = m
        _draft = State(initialValue: draft)
    }

    var body: some View {
        NavigationStack {
            Form {
                if draft.card == nil && m.books.count > 1 {
                    Picker("Adressbuch", selection: $draft.book) {
                        ForEach(m.books) { b in Text(verbatim: b.name).tag(b.id) }
                    }
                }
                Section {
                    TextField("Vorname", text: $draft.given)
                    TextField("Nachname", text: $draft.family)
                    TextField("Firma", text: $draft.org)
                    TextField("Position", text: $draft.title)
                    TextField("Spitzname", text: $draft.nick)
                }
                Section {
                    ForEach($draft.phones) { $p in
                        HStack {
                            Picker("", selection: $p.kind) { ForEach(KontaktArt.phone, id: \.self) { Text(KontaktArt.label($0)).tag($0) } }
                                .labelsHidden().fixedSize()
                            TextField("Telefon", text: $p.value).keyboardType(.phonePad)
                        }
                    }
                    .onDelete { draft.phones.remove(atOffsets: $0) }
                    if draft.phones.count < 8 { Button("Telefon hinzufügen") { draft.phones.append(KontaktZeile(kind: "Handy")) } }
                }
                Section {
                    ForEach($draft.emails) { $e in
                        TextField("E-Mail", text: $e.value).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    }
                    .onDelete { draft.emails.remove(atOffsets: $0) }
                    if draft.emails.count < 6 { Button("E-Mail hinzufügen") { draft.emails.append(KontaktZeile(kind: "")) } }
                }
                Section {
                    ForEach($draft.addrs) { $a in
                        VStack {
                            Picker("", selection: $a.kind) { ForEach(KontaktArt.addr, id: \.self) { Text(KontaktArt.label($0)).tag($0) } }
                                .labelsHidden()
                            TextField("Straße", text: $a.street)
                            HStack {
                                TextField("PLZ", text: $a.zip).frame(maxWidth: 90)
                                TextField("Ort", text: $a.city)
                            }
                            TextField("Land", text: $a.country)
                        }
                    }
                    .onDelete { draft.addrs.remove(atOffsets: $0) }
                    if draft.addrs.count < 4 { Button("Adresse hinzufügen") { draft.addrs.append(KontaktZeile(kind: "Privat")) } }
                }
                Section {
                    ForEach($draft.urls) { $u in
                        TextField("Webseite", text: $u.value).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    }
                    .onDelete { draft.urls.remove(atOffsets: $0) }
                    if draft.urls.count < 4 { Button("Webseite hinzufügen") { draft.urls.append(KontaktZeile(kind: "", value: "https://")) } }
                }
                Section {
                    TextField("Geburtstag (JJJJ-MM-TT)", text: $draft.bday).keyboardType(.numbersAndPunctuation)
                    TextField("Notiz", text: $draft.note, axis: .vertical).lineLimit(2...6)
                }
                if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
                if draft.card != nil {
                    Section { Button("Kontakt löschen", role: .destructive) { asking = true } }
                }
            }
            .navigationTitle(draft.card == nil ? "Neuer Kontakt" : "Kontakt bearbeiten")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { Task { await save() } }.disabled(busy || (draft.given + draft.family + draft.org).isEmpty)
                }
            }
            .confirmationDialog("Diesen Kontakt löschen? Er wird auch aus seinem Adressbuch gelöscht.", isPresented: $asking, titleVisibility: .visible) {
                Button("Kontakt löschen", role: .destructive) { Task { await remove() } }
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        if await m.save(draft.card, draft.body) != nil { dismiss() } else { error = m.error }
    }

    private func remove() async {
        guard let id = draft.card, let c = m.card(id) else { return }
        if await m.delete(c) { dismiss() } else { error = m.error }
    }
}
