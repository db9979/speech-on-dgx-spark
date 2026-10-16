import AVFoundation
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

// Chats (app/panel/chats.py, plan messenger.md): writing with the other people of this Spark like in a messenger.
// The list of chats with search, one chat with bubbles, ticks, photos, files and voice messages, reactions, answers,
// changing and taking back, "schreibt …", new chats and groups, and each chat's settings (stumm, verschwinden, name,
// members, leaving). Changes come live over /api/chats/stream while the chats are on screen (never in the
// background: while a page of the profile listens, the Spark sends no notification). What others write is their
// text: it is only shown here, never acted on. Photos and voice come with this iPhone's key (never a link someone
// else could open).

/// One chat in the list (GET /api/chats).
struct ChatSummary: Identifiable, Hashable {
    let id: String
    var group = false
    var priv = false
    /// With someone on another Spark (verbund.py): text only in this version.
    var far = false
    var title = ""
    var unread = 0
    var muted = false
    /// The fixed group "Alle": nobody adds or removes members by hand.
    var fixed = false
    var preview = ""
    var date: Date?
}

/// A photo, file or voice message of a chat message.
struct ChatMedia: Hashable {
    var w = 0, h = 0, secs = 0, size = 0
    var ext = "", name = ""
}

/// One reaction under a message: the emoji, how many, and whether one of them is mine.
struct ChatReact: Hashable {
    let e: String
    var n = 1
    var me = false
}

/// The message a message answers.
struct ChatQuote: Hashable {
    let id: String
    var name = ""
    var text = ""
    var gone = false
    var kind = "text"
}

struct ChatMember: Identifiable, Hashable {
    let id: String
    var name = ""
    var admin = false
    var me = false
}

/// One line of a chat (GET /api/chats/items).
struct ChatLine: Identifiable, Hashable {
    let id: String
    var from = ""
    var name = ""
    var mine = false
    var kind = "text"
    var text = ""
    var date = Date()
    var tick = ""
    var gone = false
    var edited = false
    var sys = ""
    var media: ChatMedia?
    /// a call's line (anrufe.py): how long and whether with picture; "verschwinden": the seconds
    var secs = 0
    var video = false
    /// the people a group change names
    var who: [String] = []
    var react: [ChatReact] = []
    var reply: ChatQuote?
    var canEdit = false
    var canBack = false
    /// another Spark did not take it within 7 days (verbund.py)
    var fail = false
    /// written through the assistant ("Sag Anna, …")
    var spoken = false
    /// a private chat's box as the sending device made it (JSON, opened by ChatSec.swift)
    var box: Data?
    /// a box this iPhone cannot open (sent before it was added)
    var locked = false
    /// the key of a private attachment (from inside the box)
    var fileKey: String?
}

/// One page of a chat with what the screen needs to draw it.
struct ChatPage: Equatable {
    var title = ""
    var kind = "one"
    var lines: [ChatLine] = []
    var more = false
    var canSend = false
    var why = ""
    var members: [ChatMember] = []
    var admin = false
    var vanish = 0
    /// stumm: 0 off, -1 always, else until this time
    var mute: Double = 0
    var reactions: [String] = []
    var priv = false
    var fixed = false
    var far = false
    /// a group with other Sparks that another Spark manages
    var farHome = false

    var group: Bool { kind == "group" }
}

/// A hit of the search over the own chats (POST /api/chats/find, the words never in an address).
struct ChatHit: Identifiable, Hashable {
    var id: String { chat + "/" + mid }
    let chat: String
    let mid: String
    var title = ""
    var name = ""
    var text = ""
    var date = Date()
}

struct ChatState {
    var enabled = false
    var on = false
    var media = false
    var groups = false
    /// private chats (Ende-zu-Ende) are on for this profile
    var priv = false
    var chats: [ChatSummary] = []
    var contacts: [Recipient] = []
    var maxText = 4000
    var maxMembers = 50
    /// Takes part in the fixed group "Alle" (Nachricht an alle).
    var all = false
}

/// The fixed choices of chats.py (MUTE, VANISH).
enum ChatChoice {
    struct Choice: Identifiable, Hashable {
        let id: Int
        let text: String
    }

    static var mute: [Choice] {
        [Choice(id: 0, text: String(localized: "aus")), Choice(id: 3600, text: String(localized: "1 Stunde")),
         Choice(id: 8 * 3600, text: String(localized: "8 Stunden")), Choice(id: -1, text: String(localized: "immer"))]
    }

    static var vanish: [Choice] {
        [Choice(id: 0, text: String(localized: "aus")), Choice(id: 86400, text: String(localized: "nach 24 Stunden")),
         Choice(id: 7 * 86400, text: String(localized: "nach 7 Tagen")), Choice(id: 90 * 86400, text: String(localized: "nach 90 Tagen"))]
    }

    static func vanishText(_ secs: Int) -> String { vanish.first { $0.id == secs }?.text ?? "" }

    static func kindWord(_ kind: String) -> String {
        switch kind {
        case "photo": return "📷 " + String(localized: "Foto")
        case "file": return "📄 " + String(localized: "Datei")
        case "voice": return "🎤 " + String(localized: "Sprachnachricht")
        case "box": return "🔒 " + String(localized: "Private Nachricht")
        default: return ""
        }
    }
}

extension SparkAPI {
    func chats() async throws -> ChatState {
        let (data, response) = try await URLSession.shared.data(for: request("api/chats"))
        try Self.check(data, response)
        let d = Self.object(data)
        var s = ChatState()
        s.enabled = d["enabled"] as? Bool ?? false
        s.on = d["on"] as? Bool ?? false
        s.media = d["media"] as? Bool ?? false
        s.groups = d["groups"] as? Bool ?? false
        s.priv = d["private"] as? Bool ?? false
        s.maxText = (d["max_text"] as? NSNumber)?.intValue ?? 4000
        s.maxMembers = (d["max_members"] as? NSNumber)?.intValue ?? 50
        s.all = d["all"] as? Bool ?? false
        s.chats = (d["chats"] as? [[String: Any]] ?? []).compactMap { x in
            guard let id = x["id"] as? String else { return nil }
            var c = ChatSummary(id: id)
            c.group = x["kind"] as? String == "group"
            c.priv = x["private"] as? Bool ?? false
            c.far = x["far"] as? Bool ?? false
            c.title = String((x["title"] as? String ?? "").prefix(60))
            c.unread = (x["unread"] as? NSNumber)?.intValue ?? 0
            c.muted = ((x["mute"] as? NSNumber)?.doubleValue ?? 0) != 0
            c.fixed = x["fixed"] as? Bool ?? false
            if let l = x["last"] as? [String: Any] {
                c.date = Date(timeIntervalSince1970: (l["t"] as? NSNumber)?.doubleValue ?? 0)
                c.preview = Self.preview(l, group: c.group)
            }
            return c
        }
        s.contacts = (d["contacts"] as? [[String: Any]] ?? []).compactMap { x in
            guard let id = x["id"] as? String else { return nil }
            return Recipient(id: id, name: String((x["name"] as? String ?? id).prefix(60)),
                             call: String((x["call"] as? String ?? "").prefix(60)))
        }
        return s
    }

    private static func preview(_ l: [String: Any], group: Bool) -> String {
        if l["gone"] as? Bool == true { return String(localized: "Nachricht zurückgenommen") }
        let kind = l["kind"] as? String ?? "text"
        if kind == "sys" { return String(localized: "Änderung im Chat") }
        let who = l["mine"] as? Bool == true ? String(localized: "Du: ") : group ? "\(l["name"] as? String ?? ""): " : ""
        let text = String((l["text"] as? String ?? "").prefix(120))
        switch kind {
        case "photo": return who + "📷 " + (text.isEmpty ? String(localized: "Foto") : text)
        case "file": return who + "📄 " + (text.isEmpty ? String(localized: "Datei") : text)
        case "voice": return who + "🎤 " + String(localized: "Sprachnachricht")
        case "box": return who + "🔒 " + String(localized: "Private Nachricht")
        default: return who + text
        }
    }

    private static func chatLine(_ x: [String: Any]) -> ChatLine? {
        guard let mid = x["id"] as? String else { return nil }
        var l = ChatLine(id: mid)
        l.from = x["from"] as? String ?? ""
        l.name = String((x["name"] as? String ?? "").prefix(60))
        l.mine = x["mine"] as? Bool ?? false
        l.kind = x["kind"] as? String ?? "text"
        l.text = String((x["text"] as? String ?? "").prefix(4000))
        l.date = Date(timeIntervalSince1970: (x["t"] as? NSNumber)?.doubleValue ?? 0)
        l.tick = x["tick"] as? String ?? ""
        l.gone = x["gone"] as? Bool ?? false
        l.edited = x["edited"] as? Bool ?? false
        l.sys = x["sys"] as? String ?? ""
        l.secs = (x["secs"] as? NSNumber)?.intValue ?? 0
        l.video = x["video"] as? Bool ?? false
        l.who = (x["who"] as? [String] ?? []).prefix(50).map { String($0.prefix(60)) }
        l.canEdit = x["can_edit"] as? Bool ?? false
        l.canBack = x["can_back"] as? Bool ?? false
        l.fail = x["fail"] as? Bool ?? false
        l.spoken = x["via"] as? String == "spark"
        l.react = (x["react"] as? [[String: Any]] ?? []).prefix(8).compactMap { r in
            guard let e = r["e"] as? String, !e.isEmpty, e.count <= 4 else { return nil }
            return ChatReact(e: e, n: (r["n"] as? NSNumber)?.intValue ?? 1, me: r["me"] as? Bool ?? false)
        }
        if let r = x["reply"] as? [String: Any], let rid = r["id"] as? String {
            l.reply = ChatQuote(id: rid, name: String((r["name"] as? String ?? "").prefix(60)),
                                text: String((r["text"] as? String ?? "").prefix(160)), gone: r["gone"] as? Bool ?? false,
                                kind: String((r["kind"] as? String ?? "text").prefix(10)))
        }
        if l.kind == "box" && !l.gone, let b = x["box"] as? [String: Any] {   // private chat (chatsec.py): ChatSec.swift opens it
            l.box = try? JSONSerialization.data(withJSONObject: b)
            l.canEdit = false
        }
        if let m = x["media"] as? [String: Any] {
            l.media = ChatMedia(w: (m["w"] as? NSNumber)?.intValue ?? 0, h: (m["h"] as? NSNumber)?.intValue ?? 0,
                                secs: (m["secs"] as? NSNumber)?.intValue ?? 0, size: (m["size"] as? NSNumber)?.intValue ?? 0,
                                ext: String((m["ext"] as? String ?? "").prefix(8)), name: String((m["name"] as? String ?? "").prefix(120)))
        }
        return l
    }

    /// One page of a chat: the newest, or the one before the message `before`.
    func chatItems(_ id: String, before: String = "") async throws -> ChatPage {
        var c = URLComponents(url: base.appendingPathComponent("api/chats/items"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: id)] + (before.isEmpty ? [] : [URLQueryItem(name: "before", value: before)])
        var r = request("api/chats/items")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        var p = ChatPage()
        p.kind = d["kind"] as? String ?? "one"
        p.title = String((d["title"] as? String ?? "").prefix(60))
        p.lines = (d["items"] as? [[String: Any]] ?? []).compactMap(Self.chatLine)
        p.more = d["more"] as? Bool ?? false
        p.members = (d["members"] as? [[String: Any]] ?? []).prefix(60).compactMap { x in
            guard let id = x["id"] as? String else { return nil }
            return ChatMember(id: id, name: String((x["name"] as? String ?? "").prefix(60)), admin: x["admin"] as? Bool ?? false,
                              me: x["me"] as? Bool ?? false)
        }
        p.admin = d["admin"] as? Bool ?? false
        p.vanish = (d["vanish"] as? NSNumber)?.intValue ?? 0
        p.mute = (d["mute"] as? NSNumber)?.doubleValue ?? 0
        p.reactions = (d["reactions"] as? [String] ?? []).prefix(8).filter { $0.count <= 4 }
        p.fixed = d["fixed"] as? Bool ?? false
        p.far = d["far"] as? Bool ?? false
        p.farHome = d["far_home"] as? Bool ?? false
        p.priv = d["private"] as? Bool ?? false
        if p.priv { p.title = "🔒 " + p.title }
        p.canSend = d["can_send"] as? Bool ?? false
        p.why = String((d["why"] as? String ?? "").prefix(200))
        return p
    }

    func chatOpen(to: String) async throws -> String {
        try await post("api/chats/open", ["to": to])["id"] as? String ?? ""
    }

    func chatSend(_ id: String, text: String, reply: String = "") async throws {
        var b: [String: Any] = ["id": id, "text": text]
        if !reply.isEmpty { b["reply"] = reply }
        _ = try await post("api/chats/send", b)
    }

    func chatEdit(_ id: String, mid: String, text: String) async throws {
        _ = try await post("api/chats/edit", ["id": id, "mid": mid, "text": text])
    }

    /// Takes a message back for everybody (within an hour).
    func chatBack(_ id: String, mid: String) async throws {
        _ = try await post("api/chats/back", ["id": id, "mid": mid])
    }

    /// One of the Spark's reactions; "" takes the own one away.
    func chatReact(_ id: String, mid: String, emoji: String) async throws {
        _ = try await post("api/chats/react", ["id": id, "mid": mid, "emoji": emoji])
    }

    func chatRead(_ id: String) async throws {
        _ = try await post("api/chats/read", ["id": id])
    }

    func chatTyping(_ id: String) async throws {
        _ = try await post("api/chats/typing", ["id": id])
    }

    /// "mute", "vanish" or a group's "name".
    func chatOptions(_ id: String, _ opts: [String: Any]) async throws {
        var b = opts
        b["id"] = id
        _ = try await post("api/chats/opts", b)
    }

    /// A group's admins add, take out and make admins; the names of who could not come in.
    func chatMembers(_ id: String, add: [String] = [], remove: [String] = [], admin: [String] = []) async throws -> [String] {
        let d = try await post("api/chats/members", ["id": id, "add": add, "remove": remove, "admin": admin])
        return (d["left_out"] as? [String] ?? []).prefix(50).map { String($0.prefix(60)) }
    }

    func chatLeave(_ id: String) async throws {
        _ = try await post("api/chats/leave", ["id": id])
    }

    /// Empties the chat for this profile only.
    func chatClear(_ id: String) async throws {
        _ = try await post("api/chats/clear", ["id": id])
    }

    /// A new group with this profile as its admin: its id and the names of who could not come in.
    func chatGroup(name: String, members: [String]) async throws -> (String, [String]) {
        let d = try await post("api/chats/group", ["name": name, "members": members])
        return (d["id"] as? String ?? "", (d["left_out"] as? [String] ?? []).prefix(50).map { String($0.prefix(60)) })
    }

    func chatFind(_ q: String) async throws -> [ChatHit] {
        let d = try await post("api/chats/find", ["q": String(q.prefix(200))])
        return (d["hits"] as? [[String: Any]] ?? []).prefix(30).compactMap { x in
            guard let cid = x["id"] as? String, let mid = x["mid"] as? String else { return nil }
            return ChatHit(chat: cid, mid: mid, title: String((x["title"] as? String ?? "").prefix(60)),
                           name: String((x["name"] as? String ?? "").prefix(60)), text: String((x["text"] as? String ?? "").prefix(160)),
                           date: Date(timeIntervalSince1970: (x["t"] as? NSNumber)?.doubleValue ?? 0))
        }
    }

    /// A photo (JPEG), file or recorded voice message as the raw body; a file's name in a header, never in the address.
    func chatMedia(_ id: String, kind: String, data: Data, name: String = "", reply: String = "") async throws {
        var c = URLComponents(url: base.appendingPathComponent("api/chats/media"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: id), URLQueryItem(name: "kind", value: kind)]
            + (reply.isEmpty ? [] : [URLQueryItem(name: "reply", value: reply)])
        var r = request("api/chats/media", method: "POST")
        r.url = c.url
        r.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        if !name.isEmpty {
            r.setValue(String(name.prefix(200)).addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "", forHTTPHeaderField: "X-Chat-Name")
        }
        r.httpBody = data
        let (body, response) = try await URLSession.shared.data(for: r)
        try Self.check(body, response)
    }

    /// The bytes of a photo ("t" preview, "f" full), a file or a voice message.
    func chatMediaData(_ id: String, mid: String, part: String = "f") async throws -> Data {
        var c = URLComponents(url: base.appendingPathComponent("api/chats/media"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: id), URLQueryItem(name: "mid", value: mid), URLQueryItem(name: "part", value: part)]
        var r = request("api/chats/media")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return data
    }
}

// ---------------------------------------------------------------- live changes
/// The Chats stream while chats are on screen and the app is in front: only which chat changed and who is typing,
/// never a text. In the background it is closed, so the Spark sends its notifications again.
@MainActor
final class ChatFeed: ObservableObject {
    static let shared = ChatFeed()

    struct Typer: Equatable {
        let name: String
        let until: Date
    }

    /// grows by one with each change of a chat
    @Published private(set) var changed: [String: Int] = [:]
    @Published private(set) var listChanged = 0
    @Published private(set) var typing: [String: Typer] = [:]
    /// the stream is open (the screens then ask much less often by themselves)
    @Published private(set) var live = false

    private var users = 0
    private var front = true
    private var task: Task<Void, Never>?
    private var watchers: [NSObjectProtocol] = []

    private init() {
        let nc = NotificationCenter.default
        watchers = [
            nc.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated {
                    self?.front = false
                    self?.stop()
                }
            },
            nc.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated {
                    self?.front = true
                    self?.go()
                    self?.listChanged += 1   // what came while away
                }
            },
        ]
    }

    func join() {
        users += 1
        go()
    }

    func leave() {
        users = max(0, users - 1)
        if users == 0 { stop() }
    }

    private func go() {
        guard users > 0, front, task == nil else { return }
        task = Task { [weak self] in await self?.run() }
    }

    private func stop() {
        task?.cancel()
        task = nil
        live = false
        typing = [:]
    }

    private func run() async {
        var wait: Double = 2
        while !Task.isCancelled {
            guard let api = SparkAPI.current else {
                try? await Task.sleep(for: .seconds(15))
                continue
            }
            let began = Date()
            do {
                for try await ev in api.chatEvents() {
                    live = true
                    event(ev)
                }
            } catch {}
            live = false
            // the stream ends after half an hour on its own; a quick end means trouble: wait longer each time
            wait = Date().timeIntervalSince(began) > 60 ? 2 : min(wait * 2, 60)
            try? await Task.sleep(for: .seconds(wait))
        }
    }

    private func event(_ ev: [String: Any]) {
        guard let type = ev["type"] as? String, let id = ev["id"] as? String, id.count <= 64 else { return }
        if type == "keys" {   // private chats (chatsec.py): a new device, or the history came for this one
            if !id.isEmpty { changed[id, default: 0] += 1 }
            listChanged += 1
            return
        }
        guard !id.isEmpty else { return }
        if type == "typing" {
            let secs = min(10, max(1, (ev["secs"] as? NSNumber)?.doubleValue ?? 6))
            typing[id] = Typer(name: String((ev["name"] as? String ?? "").prefix(60)), until: Date().addingTimeInterval(secs))
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(secs + 0.2))
                if let self, let t = self.typing[id], t.until <= Date() { self.typing[id] = nil }
            }
            return
        }
        if type.hasPrefix("call") && type != "call_end" { return }   // the call's own signals (Calls.swift)
        if type == "verbund" { return }
        typing[id] = nil
        changed[id, default: 0] += 1
        listChanged += 1
    }
}

// ---------------------------------------------------------------- the list
@MainActor
final class ChatsModel: ObservableObject {
    @Published var state = ChatState()
    @Published var loading = true
    @Published var error: String?
    @Published var hits: [ChatHit] = []
    @Published var finding = false
    private var soon: Task<Void, Never>?

    var unread: Int { state.chats.filter { !$0.muted }.reduce(0) { $0 + $1.unread } }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            state = try await api.chats()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// Several changes in a row load the list once.
    func loadSoon() {
        soon?.cancel()
        soon = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(200))
            guard !Task.isCancelled else { return }
            await self?.load()
        }
    }

    func find(_ q: String) async {
        let q = q.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2, let api = SparkAPI.current else {
            hits = []
            return
        }
        finding = true
        defer { finding = false }
        do {
            hits = try await api.chatFind(q)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct ChatsView: View {
    @StateObject private var m = ChatsModel()
    @ObservedObject private var feed = ChatFeed.shared
    @Environment(\.dismiss) private var dismiss
    @State private var path: [String] = []
    @State private var picking = false
    @State private var grouping = false
    @State private var query = ""
    @State private var note: String?
    @State private var privateNew = false
    @State private var ask: CodeRequest?
    @State private var newDevice: OwnKey?
    @State private var sharing = false
    @State private var shareNote: String?
    @State private var refusing = false
    @State private var keysAt = Date.distantPast

    private var searching: Bool { query.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 }

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let nk = newDevice { transfer(nk) }
                if let n = shareNote { Text(verbatim: "🔒 " + n).foregroundStyle(.secondary) }
                if m.loading {
                    ProgressView()
                } else if !m.state.on {
                    Text(SparkAPI.way(m.state.enabled
                        ? String(localized: "Chats hat der Admin für dich gesperrt.")
                        : String(localized: "Chats sind auf dem Spark aus. Der Admin schaltet sie unter Funktionen → Chats ein.")))
                } else if searching {
                    if m.hits.isEmpty && !m.finding {
                        Text("Nichts gefunden.").foregroundStyle(.secondary)
                    }
                    ForEach(m.hits) { h in
                        NavigationLink(value: h.chat) {
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(verbatim: h.title).font(.headline).lineLimit(1)
                                    Spacer()
                                    Text(verbatim: h.date.formatted(.dateTime.day().month())).font(.caption).foregroundStyle(.secondary)
                                }
                                Text(verbatim: (h.name.isEmpty ? "" : h.name + ": ") + h.text).font(.subheadline)
                                    .foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                    }
                } else if m.state.chats.isEmpty {
                    Text("Noch keine Chats. Mit ＋ schreibst du jemandem.").foregroundStyle(.secondary)
                } else {
                    ForEach(m.state.chats) { c in
                        NavigationLink(value: c.id) { ChatRow(c: c) }
                    }
                }
                if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .navigationTitle("Chats")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .automatic), prompt: Text("In Chats suchen"))
            .task(id: query) {
                guard searching else {
                    m.hits = []
                    return
                }
                try? await Task.sleep(for: .milliseconds(500))   // after the typing pauses
                guard !Task.isCancelled else { return }
                await m.find(query)
            }
            .navigationDestination(for: String.self) { id in
                let c = m.state.chats.first { $0.id == id }
                // calls only in a chat of two on this Spark (anrufe.py); "new chat" opens one of two as well
                ChatThreadView(id: id, title: c?.title ?? "", media: m.state.media, maxText: m.state.maxText,
                               callable: Conversation.shared.allowed.calls && !(c?.group ?? false) && !(c?.far ?? false),
                               contacts: m.state.contacts)
            }
            .refreshable { await m.load() }
            .task {
                // fresh while the list is open: live over the stream, asking by itself only now and then
                while !Task.isCancelled {
                    await m.load()
                    try? await Task.sleep(for: .seconds(feed.live ? 120 : 15))
                }
            }
            .onAppear { feed.join() }
            .onDisappear { feed.leave() }
            .onChange(of: feed.listChanged) { m.loadSoon() }
            .onChange(of: m.state.chats) { Task { await checkDevices() } }
            .codeAlert($ask)
            .confirmationDialog("Dieses neue Gerät aus den privaten Chats nehmen? Es kann sie danach nicht mehr lesen.",
                                isPresented: $refusing, titleVisibility: .visible) {
                Button("Nicht ich", role: .destructive) {
                    guard let nk = newDevice else { return }
                    Task {
                        do { try await ChatSec.shared.removeDevice(nk.id) } catch { m.error = error.localizedDescription }
                        newDevice = ChatSec.shared.newDevice
                    }
                }
            }
            .onChange(of: path) { if path.isEmpty { Task { await m.load() } } }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
                if m.state.on {
                    ToolbarItem(placement: .topBarLeading) {
                        if m.state.groups {
                            Menu {
                                Button { picking = true } label: { Label("Neuer Chat", systemImage: "person") }
                                Button { grouping = true } label: { Label("Neue Gruppe", systemImage: "person.3") }
                            } label: { Image(systemName: "square.and.pencil") }
                                .accessibilityLabel("Neuer Chat")
                        } else {
                            Button { picking = true } label: { Image(systemName: "square.and.pencil") }
                                .accessibilityLabel("Neuer Chat")
                        }
                    }
                }
            }
            .sheet(isPresented: $picking) {
                NavigationStack {
                    List {
                        if m.state.priv {
                            Section {
                                Toggle("Privat (Ende-zu-Ende)", isOn: $privateNew)
                            } footer: {
                                Text("Nur eure beiden Geräte können einen privaten Chat lesen, der Spark nicht.")
                            }
                        }
                        Section {
                            if m.state.contacts.isEmpty { nobody }
                            ForEach(m.state.contacts) { p in
                                Button(p.name) { Task { await open(p) } }
                            }
                        }
                    }
                    .navigationTitle("Neuer Chat")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { picking = false } } }
                }
                .presentationDetents([.medium, .large])
            }
            .sheet(isPresented: $grouping) {
                NewGroupView(people: m.state.contacts, most: m.state.maxMembers - 1) { id, left in
                    grouping = false
                    note = left.isEmpty ? nil : String(localized: "Nicht dabei, weil sie gerade keine Nachrichten von dir annehmen oder schon in zu vielen Gruppen sind: ") + left.joined(separator: ", ")
                    await m.load()
                    path = [id]
                }
            }
        }
    }

    private func open(_ p: Recipient) async {
        guard let api = SparkAPI.current else { return }
        do {
            let id: String
            if privateNew {
                if ChatSec.shared.kid == nil { _ = try await ChatSec.shared.device() }
                if ChatSec.shared.kid == nil {   // this iPhone needs its key first: the code window, then the chat
                    picking = false
                    ask = CodeRequest { code in
                        do {
                            try await ChatSec.shared.addDevice(code: code)
                            let id = try await ChatSec.shared.start(with: p.id)
                            await m.load()
                            path = [id]
                        } catch {
                            m.error = error.localizedDescription
                        }
                    }
                    return
                }
                id = try await ChatSec.shared.start(with: p.id)
            } else {
                id = try await api.chatOpen(to: p.id)
            }
            picking = false
            await m.load()
            path = [id]
        } catch {
            m.error = error.localizedDescription
            picking = false
        }
    }

    /// An older device offers the history to a new one of the same person (at most every 30 seconds).
    private func checkDevices() async {
        guard m.state.priv, !sharing, Date().timeIntervalSince(keysAt) > 30 else { return }
        keysAt = Date()
        _ = try? await ChatSec.shared.device()
        newDevice = ChatSec.shared.newDevice
    }

    @ViewBuilder private func transfer(_ nk: OwnKey) -> some View {
        Section {
            Text(verbatim: "🔒 " + String(localized: "Neues Gerät") + ": " + PrivateInfo.kindName(nk.kind) + ", "
                 + Date(timeIntervalSince1970: TimeInterval(nk.t)).formatted(date: .abbreviated, time: .shortened)).font(.headline)
            Text("Verlauf deiner privaten Chats dorthin übertragen? Nur wenn dort derselbe Code steht: \(ChatSec.code(nk.pub))")
                .font(.subheadline)
            HStack {
                Button("Übertragen") {
                    let list = m.state.chats.filter(\.priv).map(\.id)
                    sharing = true
                    Task {
                        do {
                            let n = try await ChatSec.shared.share(to: nk, chats: list) { done in
                                shareNote = String(localized: "Übertragen: ") + "\(done) / \(list.count)"
                            }
                            shareNote = String(localized: "Verlauf übertragen: \(n) Nachrichten")
                        } catch {
                            shareNote = error.localizedDescription
                        }
                        sharing = false
                        newDevice = ChatSec.shared.newDevice
                    }
                }
                .buttonStyle(.borderedProminent)
                Spacer()
                Button("Nicht ich", role: .destructive) { refusing = true }
                    .buttonStyle(.borderless)
            }
            .disabled(sharing)
        }
    }

    private var nobody: some View {
        Text(SparkAPI.way(String(localized: "Niemand nimmt gerade Nachrichten von dir an. Jede Person legt unter Ich → Gespräch → Chats fest, wer ihr schreiben darf.")))
            .foregroundStyle(.secondary)
    }
}

private struct ChatRow: View {
    let c: ChatSummary

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: c.group ? "person.3.fill" : "person.crop.circle.fill")
                .font(.title2)
                .foregroundStyle(.secondary)
                .frame(width: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: (c.priv ? "🔒 " : "") + (c.far ? "🌐 " : "") + c.title).font(.headline).lineLimit(1)
                Text(verbatim: c.preview).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 4) {
                if let d = c.date {
                    Text(verbatim: Calendar.current.isDateInToday(d) ? d.formatted(date: .omitted, time: .shortened)
                                                                       : d.formatted(.dateTime.day().month()))
                        .font(.caption).foregroundStyle(.secondary)
                }
                HStack(spacing: 4) {
                    if c.muted { Image(systemName: "bell.slash").font(.caption).foregroundStyle(.secondary) }
                    if c.unread > 0 {
                        Text(verbatim: c.unread > 99 ? "99+" : String(c.unread))
                            .font(.caption.bold()).foregroundStyle(.white)
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(Capsule().fill(c.muted ? Color.gray : Color.accentColor))
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// Picks people from those who take messages from this profile (a new group, adding to a group).
private struct PeoplePicker: View {
    let people: [Recipient]
    let most: Int
    @Binding var picked: Set<String>

    var body: some View {
        ForEach(people) { p in
            Button {
                if picked.contains(p.id) { picked.remove(p.id) } else if picked.count < most { picked.insert(p.id) }
            } label: {
                HStack {
                    Text(verbatim: p.name).foregroundStyle(.primary)
                    Spacer()
                    if picked.contains(p.id) { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
                }
            }
            .accessibilityAddTraits(picked.contains(p.id) ? .isSelected : [])
        }
    }
}

private struct NewGroupView: View {
    let people: [Recipient]
    let most: Int
    let made: @MainActor (String, [String]) async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var picked = Set<String>()
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Name der Gruppe", text: $name)
                        .onChange(of: name) { _, n in if n.count > 40 { name = String(n.prefix(40)) } }
                }
                Section {
                    if people.isEmpty {
                        Text(SparkAPI.way(String(localized: "Niemand nimmt gerade Nachrichten von dir an. Jede Person legt unter Ich → Gespräch → Chats fest, wer ihr schreiben darf.")))
                            .foregroundStyle(.secondary)
                    }
                    PeoplePicker(people: people, most: most, picked: $picked)
                } header: {
                    Text("Wer kommt in die Gruppe")
                } footer: {
                    Text("Du bist Admin der Gruppe. Dabei sein kann nur, wer Nachrichten von dir annimmt.")
                }
                if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .navigationTitle("Neue Gruppe")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Erstellen") {
                        Task {
                            guard let api = SparkAPI.current else { return }
                            busy = true
                            defer { busy = false }
                            do {
                                let (id, left) = try await api.chatGroup(name: name.trimmingCharacters(in: .whitespaces), members: Array(picked))
                                await made(id, left)
                            } catch {
                                self.error = error.localizedDescription
                            }
                        }
                    }
                    .disabled(busy || name.trimmingCharacters(in: .whitespaces).isEmpty || picked.isEmpty)
                }
            }
        }
    }
}

// ---------------------------------------------------------------- one chat
@MainActor
final class ChatThreadModel: ObservableObject {
    let id: String
    @Published var page = ChatPage()
    /// pages loaded with "Ältere Nachrichten" (the live page is always the newest)
    @Published var older: [ChatLine] = []
    @Published var moreOlder = false
    @Published var text = ""
    @Published var reply: ChatLine?
    @Published var editing: ChatLine?
    @Published var busy = false
    @Published var error: String?
    /// a private chat and this iPhone has no key for it yet
    @Published var needKey = false
    /// a private chat with messages this iPhone cannot open while it waits for the history: the code to compare
    @Published var historyCode: String?
    private var readUpTo = ""
    private var typedAt = Date.distantPast
    private var soon: Task<Void, Never>?

    init(id: String, title: String) {
        self.id = id
        page.title = title
    }

    var lines: [ChatLine] {
        let ids = Set(page.lines.map(\.id))
        return older.filter { !ids.contains($0.id) } + page.lines
    }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            var p = try await api.chatItems(id)
            if p.title.isEmpty { p.title = page.title }
            if p.priv { await openBoxes(&p) }
            if older.isEmpty { moreOlder = p.more }
            if p != page { page = p }
            error = nil
            // read only when someone else wrote something new: a read tells the other pages, so not on every load
            if let last = p.lines.last(where: { !$0.mine && $0.kind != "sys" }), last.id != readUpTo,
               UIApplication.shared.applicationState == .active {
                readUpTo = last.id
                try? await api.chatRead(id)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Private chat: the boxes become text for this iPhone (ChatSec.swift); without a key it can neither read nor write.
    private func openBoxes(_ p: inout ChatPage) async {
        let sec = ChatSec.shared
        let ok = await sec.prepare(id, &p.lines)
        needKey = sec.kid == nil
        if !ok {
            p.canSend = false
            p.why = needKey ? "" : String(localized: "Die Schlüssel für private Chats sind gerade nicht zu holen.")
        }
        if let m = sec.mine, m.want, p.lines.contains(where: \.locked) { historyCode = ChatSec.code(m.pub) } else { historyCode = nil }
    }

    /// This iPhone gets its own key for private chats (the profile's code when it has a second step).
    func addDevice(_ code: String) async {
        if await run({ _ in try await ChatSec.shared.addDevice(code: code) }) { await load() }
    }

    func loadSoon() {
        soon?.cancel()
        soon = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            await self?.load()
        }
    }

    func loadOlder() async {
        guard let api = SparkAPI.current, let first = lines.first, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            var p = try await api.chatItems(id, before: first.id)
            if p.priv { _ = await ChatSec.shared.prepare(id, &p.lines) }
            older = p.lines + older
            moreOlder = p.more
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func run(_ work: (SparkAPI) async throws -> Void) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        do {
            try await work(api)
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func send(max: Int) async {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !busy else { return }
        busy = true
        defer { busy = false }
        let edit = editing, answer = reply, priv = page.priv
        let ok = await run { api in
            if priv {
                try await ChatSec.shared.send(id, text: String(t.prefix(max)), reply: answer?.id ?? "")
            } else if let e = edit {
                try await api.chatEdit(id, mid: e.id, text: String(t.prefix(max)))
            } else {
                try await api.chatSend(id, text: String(t.prefix(max)), reply: answer?.id ?? "")
            }
        }
        if ok {
            text = ""
            editing = nil
            reply = nil
            await load()
        }
    }

    /// "schreibt …" for the others, at most every 4 seconds while typing.
    func typed() {
        guard editing == nil, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              Date().timeIntervalSince(typedAt) > 4, let api = SparkAPI.current else { return }
        typedAt = Date()
        let cid = id
        Task { try? await api.chatTyping(cid) }
    }

    func react(_ l: ChatLine, _ e: String) async {
        let mine = l.react.contains { $0.me && $0.e == e }
        if await run({ api in try await api.chatReact(id, mid: l.id, emoji: mine ? "" : e) }) { await load() }
    }

    func takeBack(_ l: ChatLine) async {
        if await run({ api in try await api.chatBack(id, mid: l.id) }) {
            if editing?.id == l.id { stopWriting() }
            await load()
        }
    }

    func startReply(_ l: ChatLine) {
        if editing != nil { text = "" }
        editing = nil
        reply = l
    }

    func startEdit(_ l: ChatLine) {
        reply = nil
        editing = l
        text = l.text
    }

    func stopWriting() {
        if editing != nil { text = "" }
        editing = nil
        reply = nil
    }

    func options(_ o: [String: Any]) async -> Bool {
        let ok = await run { api in try await api.chatOptions(id, o) }
        if ok { await load() }
        return ok
    }

    /// nil when it failed, else the names of who could not come in
    func members(add: [String] = [], remove: [String] = [], admin: [String] = []) async -> [String]? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let left = try await api.chatMembers(id, add: add, remove: remove, admin: admin)
            error = nil
            await load()
            return left
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    func leave() async -> Bool { await run { api in try await api.chatLeave(id) } }

    func clear() async -> Bool {
        let ok = await run { api in try await api.chatClear(id) }
        if ok {
            older = []
            await load()
        }
        return ok
    }

    func sendPhoto(_ item: PhotosPickerItem) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let answer = reply?.id ?? "", priv = page.priv
        let ok = await run { api in
            if priv {   // drawn anew on this iPhone and sent under its own key (ChatSec.swift)
                guard let raw = try await item.loadTransferable(type: Data.self) else {
                    throw SparkError(message: String(localized: "Das Foto kann ich nicht laden."))
                }
                try await ChatSec.shared.upload(id, kind: "photo", data: raw, reply: answer)
                return
            }
            // the Spark saves it anew without place data; JPEG here so HEIC from the camera fits too
            guard let raw = try await item.loadTransferable(type: Data.self), let image = UIImage(data: raw),
                  let jpeg = image.jpegData(compressionQuality: 0.85) else {
                throw SparkError(message: String(localized: "Das Foto kann ich nicht laden."))
            }
            try await api.chatMedia(id, kind: "photo", data: jpeg, reply: answer)
        }
        if ok {
            reply = nil
            await load()
        }
    }

    func sendFile(_ url: URL) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let open = url.startAccessingSecurityScopedResource()
        defer { if open { url.stopAccessingSecurityScopedResource() } }
        let answer = reply?.id ?? "", priv = page.priv
        let ok = await run { api in
            let data = try Data(contentsOf: url)
            if priv {
                try await ChatSec.shared.upload(id, kind: "file", data: data, name: url.lastPathComponent,
                                                mime: UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "", reply: answer)
                return
            }
            try await api.chatMedia(id, kind: "file", data: data, name: url.lastPathComponent, reply: answer)
        }
        if ok {
            reply = nil
            await load()
        }
    }
}

/// What a long press on a message offers.
enum ChatAction {
    case react(String), reply, copy, edit, back, jump(String)
}

struct ChatThreadView: View {
    @StateObject private var m: ChatThreadModel
    let media: Bool
    let maxText: Int
    let callable: Bool
    let contacts: [Recipient]
    @State private var photo: PhotosPickerItem?
    @State private var files = false
    @State private var info = false
    @State private var backing: ChatLine?
    @State private var ask: CodeRequest?
    @FocusState private var writing: Bool
    @ObservedObject private var calls = CallCenter.shared
    @ObservedObject private var feed = ChatFeed.shared
    @Environment(\.dismiss) private var dismiss

    init(id: String, title: String, media: Bool, maxText: Int, callable: Bool = false, contacts: [Recipient] = []) {
        _m = StateObject(wrappedValue: ChatThreadModel(id: id, title: title))
        self.media = media
        self.maxText = maxText
        self.callable = callable
        self.contacts = contacts
    }

    var body: some View {
        let lines = m.lines
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 6) {
                        if m.moreOlder {
                            Button("Ältere Nachrichten") { Task { await m.loadOlder() } }
                                .font(.footnote).disabled(m.busy).padding(.top, 6)
                        }
                        if m.page.vanish > 0 {
                            Text(verbatim: "⏱ " + String(localized: "Nachrichten verschwinden") + " " + ChatChoice.vanishText(m.page.vanish))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if lines.isEmpty {
                            Text(verbatim: m.page.group ? String(localized: "Die Gruppe ist da. Schreib die erste Nachricht.")
                                                        : String(localized: "Schreib die erste Nachricht."))
                                .font(.footnote).foregroundStyle(.secondary).padding(.top, 20)
                        }
                        ForEach(Array(lines.enumerated()), id: \.element.id) { i, l in
                            if i == 0 || !Calendar.current.isDate(l.date, inSameDayAs: lines[i - 1].date) {
                                Text(verbatim: Self.day(l.date)).font(.caption.bold()).foregroundStyle(.secondary)
                                    .padding(.horizontal, 10).padding(.vertical, 3)
                                    .background(Capsule().fill(Color(.secondarySystemBackground)))
                                    .padding(.vertical, 4)
                            }
                            ChatBubble(chat: m.id, l: l,
                                       showName: m.page.group && !l.mine && (i == 0 || lines[i - 1].from != l.from || lines[i - 1].kind == "sys"),
                                       reactions: m.page.canSend ? m.page.reactions : [], canAnswer: m.page.canSend) { a in
                                act(a, l, proxy)
                            }
                            .id(l.id)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: m.page.lines.last?.id) { _, last in
                    if let last { withAnimation { proxy.scrollTo(last, anchor: .bottom) } }
                }
                .onAppear { if let last = lines.last?.id { proxy.scrollTo(last, anchor: .bottom) } }
            }
            if let e = m.error {
                Text(SparkAPI.way(e)).font(.footnote).foregroundStyle(.red).padding(.horizontal).padding(.vertical, 4)
            }
            if let c = m.historyCode {
                Text("Ältere Nachrichten liegen auf deinen anderen Geräten. Öffne Chats auf einem davon und tippe „Übertragen“, wenn dort derselbe Code steht: \(c)")
                    .font(.footnote).foregroundStyle(.secondary).padding(.horizontal).padding(.vertical, 4)
            }
            if m.needKey {
                VStack(spacing: 8) {
                    Text("Damit du hier lesen und schreiben kannst, bekommt dieses iPhone einen eigenen Schlüssel. Er bleibt auf dem iPhone, der Spark bekommt nur seine öffentliche Hälfte.")
                        .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    Button("Dieses iPhone eintragen") { ask = CodeRequest { code in await m.addDevice(code) } }
                        .buttonStyle(.borderedProminent)
                }
                .padding()
            } else if m.page.canSend { composer } else if !m.page.why.isEmpty {
                Text(verbatim: m.page.why).font(.footnote).foregroundStyle(.secondary).padding()
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Button { info = true } label: {
                    VStack(spacing: 0) {
                        Text(verbatim: m.page.title).font(.headline).lineLimit(1)
                        if let t = feed.typing[m.id] {
                            Text(verbatim: m.page.group ? String(localized: "\(t.name) schreibt …") : String(localized: "schreibt …"))
                                .font(.caption).foregroundStyle(.secondary)
                        } else if m.page.group {
                            Text("\(m.page.members.count) Personen").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .foregroundStyle(.primary)
                }
                .accessibilityLabel(Text("Chat-Infos: \(m.page.title)"))
            }
            ToolbarItemGroup(placement: .topBarTrailing) {
                if callable {
                    Button { calls.dial(chat: m.id, name: m.page.title, video: false) } label: { Image(systemName: "phone") }
                        .accessibilityLabel("Anrufen").disabled(calls.active)
                    Button { calls.dial(chat: m.id, name: m.page.title, video: true) } label: { Image(systemName: "video") }
                        .accessibilityLabel("Videoanruf").disabled(calls.active)
                }
            }
        }
        .task {
            while !Task.isCancelled {   // fresh while the chat is open: live over the stream, else every 4 seconds
                await m.load()
                try? await Task.sleep(for: .seconds(feed.live ? 60 : 4))
            }
        }
        .onAppear { feed.join() }
        .onDisappear { feed.leave() }
        .onChange(of: feed.changed[m.id]) { m.loadSoon() }
        .onChange(of: photo) {
            guard let item = photo else { return }
            photo = nil
            Task { await m.sendPhoto(item) }
        }
        .fileImporter(isPresented: $files, allowedContentTypes: [.pdf, .plainText, .commaSeparatedText, .data]) { result in
            if case .success(let url) = result { Task { await m.sendFile(url) } }
        }
        .codeAlert($ask)
        .sheet(isPresented: $info) {
            ChatInfoView(m: m, contacts: contacts) {
                info = false
                dismiss()
            }
        }
        .confirmationDialog("Für alle zurücknehmen?", isPresented: Binding(get: { backing != nil }, set: { if !$0 { backing = nil } }),
                            titleVisibility: .visible) {
            Button("Für alle zurücknehmen", role: .destructive) {
                if let l = backing { Task { await m.takeBack(l) } }
                backing = nil
            }
        } message: {
            Text("Die Nachricht verschwindet bei allen in diesem Chat. Dort steht dann, dass du sie zurückgenommen hast.")
        }
    }

    private func act(_ a: ChatAction, _ l: ChatLine, _ proxy: ScrollViewProxy) {
        switch a {
        case .react(let e): Task { await m.react(l, e) }
        case .reply:
            m.startReply(l)
            writing = true
        case .copy: UIPasteboard.general.string = l.text
        case .edit:
            m.startEdit(l)
            writing = true
        case .back: backing = l
        case .jump(let mid): withAnimation { proxy.scrollTo(mid, anchor: .center) }
        }
    }

    static func day(_ d: Date) -> String {
        if Calendar.current.isDateInToday(d) { return String(localized: "Heute") }
        if Calendar.current.isDateInYesterday(d) { return String(localized: "Gestern") }
        return d.formatted(.dateTime.weekday(.wide).day().month(.wide))
    }

    private var composer: some View {
        VStack(spacing: 0) {
            if m.reply != nil || m.editing != nil {
                HStack(spacing: 8) {
                    Image(systemName: m.editing != nil ? "pencil" : "arrowshape.turn.up.left").foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 1) {
                        if let r = m.reply {
                            Text(verbatim: r.mine ? String(localized: "Du") : r.name).font(.caption.bold())
                            Text(verbatim: r.text.isEmpty ? ChatChoice.kindWord(r.kind) : r.text).font(.caption)
                                .foregroundStyle(.secondary).lineLimit(1)
                        } else {
                            Text("Nachricht ändern").font(.caption.bold())
                        }
                    }
                    Spacer()
                    Button { m.stopWriting() } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }
                        .accessibilityLabel("Abbrechen")
                }
                .padding(.horizontal, 14).padding(.top, 6)
            }
            HStack(alignment: .bottom, spacing: 8) {
                if media && m.editing == nil {
                    Menu {
                        PhotosPicker(selection: $photo, matching: .images) { Label("Foto", systemImage: "photo") }
                        Button { files = true } label: { Label("Datei", systemImage: "doc") }
                    } label: {
                        Image(systemName: "paperclip").font(.title3).frame(width: 36, height: 36)
                    }
                    .accessibilityLabel("Foto oder Datei schicken")
                    .disabled(m.busy)
                }
                TextField("Nachricht", text: $m.text, axis: .vertical)
                    .lineLimit(1...5)
                    .focused($writing)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 18).fill(Color(.secondarySystemBackground)))
                    .onChange(of: m.text) { _, t in
                        if t.count > maxText { m.text = String(t.prefix(maxText)) }
                        m.typed()
                    }
                Button {
                    Task { await m.send(max: maxText) }
                } label: {
                    if m.busy { ProgressView().frame(width: 36, height: 36) } else {
                        Image(systemName: m.editing != nil ? "checkmark.circle.fill" : "arrow.up.circle.fill").font(.system(size: 32))
                    }
                }
                .accessibilityLabel(m.editing != nil ? Text("Ändern") : Text("Senden"))
                .disabled(m.busy || m.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
        }
        .background(.bar)
    }
}

/// ⓘ of a chat: stumm, "Nachrichten verschwinden", a group's name and members, emptying and leaving (as in the panel).
private struct ChatInfoView: View {
    @ObservedObject var m: ChatThreadModel
    let contacts: [Recipient]
    let left: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var adding = false
    @State private var picked = Set<String>()
    @State private var note: String?
    @State private var asking: Ask?

    enum Ask: Identifiable {
        case clear, leave, remove(ChatMember)
        var id: String {
            switch self {
            case .clear: return "clear"
            case .leave: return "leave"
            case .remove(let p): return "remove " + p.id
            }
        }
    }

    private var p: ChatPage { m.page }
    /// "verschwinden" for everybody: in a chat of two each of them, in a group its admins
    private var may: Bool { !p.group || (p.admin && !p.fixed) }
    private var manage: Bool { p.group && p.admin && !p.fixed && !p.farHome }
    private var muteValue: Int {
        if p.mute == -1 { return -1 }
        if p.mute <= 0 { return 0 }
        return p.mute - Date().timeIntervalSince1970 > 3 * 3600 ? 8 * 3600 : 3600
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(verbatim: p.title).font(.headline)
                    Text(verbatim: subtitle).font(.subheadline).foregroundStyle(.secondary)
                }
                if manage {
                    Section("Name") {
                        HStack {
                            TextField("Name der Gruppe", text: $name)
                                .onChange(of: name) { _, n in if n.count > 40 { name = String(n.prefix(40)) } }
                            Button("Speichern") { Task { _ = await m.options(["name": name.trimmingCharacters(in: .whitespaces)]) } }
                                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || name == p.title)
                        }
                    }
                }
                Section {
                    Picker("Stumm", selection: Binding(get: { muteValue }, set: { v in Task { _ = await m.options(["mute": v]) } })) {
                        ForEach(ChatChoice.mute) { c in Text(verbatim: c.text).tag(c.id) }
                    }
                    Picker("Nachrichten verschwinden", selection: Binding(get: { p.vanish }, set: { v in Task { _ = await m.options(["vanish": v]) } })) {
                        ForEach(ChatChoice.vanish) { c in Text(verbatim: c.text).tag(c.id) }
                    }
                    .disabled(!may)
                } footer: {
                    Text(verbatim: String(localized: "Stumm: keine Mitteilungen aufs iPhone, nur für dich.") + " "
                         + (p.fixed ? String(localized: "„Nachrichten verschwinden“: feste Gruppe ohne Admins.")
                            : may ? String(localized: "„Nachrichten verschwinden“ gilt für alle in diesem Chat.")
                            : String(localized: "„Nachrichten verschwinden“ stellen die Admins der Gruppe ein.")))
                }
                if p.priv { PrivateInfo(m: m) }
                if p.group {
                    Section {
                        ForEach(p.members) { x in
                            HStack {
                                Text(verbatim: x.me ? String(localized: "Du") : x.name.isEmpty ? String(localized: "Gelöschtes Profil") : x.name)
                                if x.admin { Text("Admin").font(.caption).foregroundStyle(.secondary) }
                            }
                            .swipeActions {
                                if manage && !x.me {
                                    Button("Entfernen", role: .destructive) { asking = .remove(x) }
                                    if !x.admin && !x.id.hasPrefix("r_") {
                                        Button("Zum Admin") { Task { _ = await m.members(admin: [x.id]) } }.tint(.blue)
                                    }
                                }
                            }
                        }
                        if manage {
                            Button {
                                picked = []
                                adding = true
                            } label: { Label("Personen hinzufügen", systemImage: "person.badge.plus") }
                        }
                    } header: {
                        Text("Mitglieder")
                    } footer: {
                        if manage { Text("Nach links wischen: zum Admin machen oder entfernen.") }
                        else if p.farHome { Text("Diese Gruppe verwaltet ein anderer Spark.") }
                    }
                }
                Section {
                    Button("Chat für mich leeren", role: .destructive) { asking = .clear }
                    if p.group {
                        Button(p.fixed ? LocalizedStringKey("Nicht mehr mitmachen") : LocalizedStringKey("Gruppe verlassen"), role: .destructive) { asking = .leave }
                    }
                }
                if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .navigationTitle("Chat-Infos")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .onAppear { name = p.title }
            .confirmationDialog(askTitle, isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } }),
                                titleVisibility: .visible, presenting: asking) { a in
                Button(askButton(a), role: .destructive) { Task { await run(a) } }
            }
            .sheet(isPresented: $adding) {
                NavigationStack {
                    List {
                        let ids = Set(p.members.map(\.id))
                        let free = contacts.filter { !ids.contains($0.id) }
                        if free.isEmpty {
                            Text("Alle, die Nachrichten von dir annehmen, sind schon dabei.").foregroundStyle(.secondary)
                        }
                        PeoplePicker(people: free, most: max(0, 50 - p.members.count), picked: $picked)
                    }
                    .navigationTitle("Personen hinzufügen")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { adding = false } }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Hinzufügen") {
                                Task {
                                    if let out = await m.members(add: Array(picked)) {
                                        note = out.isEmpty ? nil : String(localized: "Nicht dabei, weil sie gerade keine Nachrichten von dir annehmen oder schon in zu vielen Gruppen sind: ") + out.joined(separator: ", ")
                                        adding = false
                                    }
                                }
                            }
                            .disabled(picked.isEmpty)
                        }
                    }
                }
                .presentationDetents([.medium, .large])
            }
        }
    }

    private var subtitle: String {
        if p.fixed { return String(localized: "\(p.members.count) Personen · alle, die bei „Nachricht an alle“ mitmachen") }
        if p.group { return String(localized: "\(p.members.count) Personen") + (p.farHome ? " · " + String(localized: "verwaltet auf einem anderen Spark") : "") }
        if p.far { return String(localized: "Chat zu zweit mit jemandem auf einem anderen Spark") }
        if p.priv { return String(localized: "Privater Chat zu zweit, Ende-zu-Ende") }
        return String(localized: "Chat zu zweit")
    }

    private var askTitle: String {
        switch asking {
        case .clear: return String(localized: "Chat für dich leeren? Die anderen behalten ihre Nachrichten.")
        case .leave: return String(localized: "Gruppe verlassen? Zurück kommst du nur, wenn ein Admin dich wieder hinzufügt.")
        case .remove(let x): return String(localized: "\(x.name) aus der Gruppe nehmen?")
        case nil: return ""
        }
    }

    private func askButton(_ a: Ask) -> String {
        switch a {
        case .clear: return String(localized: "Leeren")
        case .leave: return p.fixed ? String(localized: "Nicht mehr mitmachen") : String(localized: "Verlassen")
        case .remove: return String(localized: "Entfernen")
        }
    }

    private func run(_ a: Ask) async {
        switch a {
        case .clear: _ = await m.clear()
        case .leave: if await m.leave() { left() }
        case .remove(let x): _ = await m.members(remove: [x.id])
        }
        asking = nil
    }
}

/// The bytes of a photo, file or voice message; a private one comes as nonce + AES-GCM and is opened with the key
/// from its box (there is no preview of it on the Spark).
@MainActor
enum ChatMediaLoad {
    static func data(_ chat: String, _ l: ChatLine, part: String = "f") async throws -> Data {
        guard let api = SparkAPI.current else { throw SparkError(message: String(localized: "Keine Antwort vom Spark.")) }
        if let k = l.fileKey { return try ChatSec.openMedia(try await api.chatMediaData(chat, mid: l.id, part: "f"), key: k) }
        return try await api.chatMediaData(chat, mid: l.id, part: part)
    }
}

/// ⓘ of a private chat: the Sicherheitsnummer to compare once, and the own devices for private chats.
private struct PrivateInfo: View {
    @ObservedObject var m: ChatThreadModel
    @State private var number = ""
    @State private var seen = false
    @State private var own: [OwnKey] = []
    @State private var kid: String?
    @State private var error: String?
    @State private var ask: CodeRequest?
    @State private var removing: OwnKey?

    var body: some View {
        Section {
            Text("Nur eure Geräte können diesen Chat lesen, der Spark nicht. Vergleicht diese Nummer einmal von Angesicht zu Angesicht oder am Telefon: Ist sie bei euch beiden gleich, sitzt niemand dazwischen.")
                .font(.footnote).foregroundStyle(.secondary)
            if !number.isEmpty {
                Text(verbatim: number).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                if seen {
                    Label("Verglichen. Ändert sich ein Schlüssel, fragt die App neu.", systemImage: "checkmark.seal").foregroundStyle(.green)
                } else {
                    Button("Ist bei uns beiden gleich") {
                        UserDefaults.standard.set(number, forKey: ChatSec.seenKey(m.id))
                        seen = true
                    }
                }
            }
        } header: {
            Text("🔒 Ende-zu-Ende")
        }
        Section {
            ForEach(own) { k in
                HStack {
                    Text(verbatim: Self.kindName(k.kind) + " · " + String(localized: "seit") + " "
                         + Date(timeIntervalSince1970: TimeInterval(k.t)).formatted(date: .abbreviated, time: .omitted))
                    if k.id == kid { Text("dieses iPhone").font(.caption).foregroundStyle(.secondary) }
                }
                .swipeActions { Button("Entfernen", role: .destructive) { removing = k } }
            }
            if own.isEmpty { Text("Noch keines.").foregroundStyle(.secondary) }
            if kid == nil {
                Button("Dieses iPhone eintragen") {
                    ask = CodeRequest { code in
                        await m.addDevice(code)
                        await refresh()
                    }
                }
            }
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        } header: {
            Text("Deine Geräte")
        } footer: {
            Text("Nach links wischen: ein Gerät aus den privaten Chats nehmen.")
        }
        .codeAlert($ask)
        .task { await refresh() }
        .confirmationDialog(removing?.id == kid ? String(localized: "Dieses iPhone aus den privaten Chats nehmen? Es kann sie danach nicht mehr lesen.")
                                                : String(localized: "Dieses Gerät aus den privaten Chats nehmen? Es kann neue Nachrichten danach nicht mehr lesen."),
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button("Entfernen", role: .destructive) {
                guard let k = removing else { return }
                removing = nil
                Task {
                    do { try await ChatSec.shared.removeDevice(k.id) } catch { self.error = error.localizedDescription }
                    await refresh()
                    await m.load()
                }
            }
        }
    }

    static func kindName(_ k: String) -> String {
        switch k {
        case "android": return String(localized: "Android-App")
        case "iphone": return String(localized: "iPhone-App")
        default: return String(localized: "Browser")
        }
    }

    private func refresh() async {
        do {
            kid = try await ChatSec.shared.device()
            own = ChatSec.shared.own
            number = try await ChatSec.shared.number(m.id)
            seen = UserDefaults.standard.string(forKey: ChatSec.seenKey(m.id)) == number
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct ChatBubble: View {
    let chat: String
    let l: ChatLine
    var showName = false
    var reactions: [String] = []
    var canAnswer = false
    let act: (ChatAction) -> Void

    var body: some View {
        if l.kind == "sys" {
            Text(verbatim: sysLine).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity).padding(.vertical, 2)
        } else {
            HStack {
                if l.mine { Spacer(minLength: 40) }
                VStack(alignment: l.mine ? .trailing : .leading, spacing: 2) {
                    bubble
                        .contextMenu { if !l.gone { menu } }
                    if !l.react.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(l.react, id: \.e) { r in
                                Button { act(.react(r.e)) } label: {
                                    Text(verbatim: r.e + (r.n > 1 ? " \(r.n)" : "")).font(.caption)
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(Capsule().fill(r.me ? Color.accentColor.opacity(0.25) : Color(.tertiarySystemBackground)))
                                }
                                .buttonStyle(.plain)
                                .disabled(reactions.isEmpty)
                            }
                        }
                    }
                }
                if !l.mine { Spacer(minLength: 40) }
            }
        }
    }

    private var bubble: some View {
        VStack(alignment: .leading, spacing: 4) {
            if showName {
                Text(verbatim: l.name.isEmpty ? String(localized: "Gelöschtes Profil") : l.name).font(.caption.bold()).foregroundStyle(.secondary)
            }
            if let q = l.reply {
                Button { act(.jump(q.id)) } label: {
                    HStack(spacing: 6) {
                        RoundedRectangle(cornerRadius: 1).fill(Color.accentColor).frame(width: 3)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(verbatim: q.name).font(.caption.bold())
                            Text(verbatim: q.gone ? String(localized: "Nachricht zurückgenommen") : q.text.isEmpty ? ChatChoice.kindWord(q.kind) : q.text)
                                .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text("Zur Nachricht, auf die das antwortet"))
            }
            if l.gone {
                Text(l.mine ? LocalizedStringKey("Du hast diese Nachricht zurückgenommen.") : LocalizedStringKey("Diese Nachricht wurde zurückgenommen."))
                    .italic().foregroundStyle(.secondary)
            } else {
                if l.kind == "photo" { ChatPhoto(chat: chat, l: l) }
                if l.kind == "voice" { ChatVoice(chat: chat, l: l) }
                if l.kind == "file", let f = l.media { ChatFile(chat: chat, l: l, f: f) }
                if !l.text.isEmpty {
                    Text(verbatim: l.text).italic(l.kind == "voice").textSelection(.enabled)
                }
            }
            HStack(spacing: 4) {
                if l.spoken { Text(verbatim: "🎙").accessibilityLabel(Text("über den Assistenten")) }
                if l.edited { Text("bearbeitet") }
                Text(l.date, format: .dateTime.hour().minute())
                if l.mine && l.fail {
                    Text(verbatim: "⚠").foregroundStyle(.orange)
                        .accessibilityLabel(Text("nicht zugestellt: der andere Spark war 7 Tage nicht erreichbar"))
                } else if l.mine && !l.tick.isEmpty {
                    Text(verbatim: l.tick == "sent" ? "✓" : "✓✓").foregroundStyle(l.tick == "read" ? Color.blue : Color.secondary)
                        .accessibilityLabel(l.tick == "read" ? Text("gelesen") : l.tick == "got" ? Text("zugestellt") : Text("gesendet"))
                }
            }
            .font(.caption2).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 16).fill(l.mine ? Color.accentColor.opacity(0.18) : Color(.secondarySystemBackground)))
    }

    @ViewBuilder private var menu: some View {
        if !reactions.isEmpty {
            Menu {
                ForEach(reactions, id: \.self) { e in
                    Button { act(.react(e)) } label: {
                        Text(verbatim: l.react.contains { $0.me && $0.e == e } ? e + " ✓" : e)
                    }
                }
            } label: { Label("Reagieren", systemImage: "face.smiling") }
        }
        if canAnswer { Button { act(.reply) } label: { Label("Antworten", systemImage: "arrowshape.turn.up.left") } }
        if !l.text.isEmpty { Button { act(.copy) } label: { Label("Kopieren", systemImage: "doc.on.doc") } }
        if l.canEdit && canAnswer { Button { act(.edit) } label: { Label("Ändern", systemImage: "pencil") } }
        if l.canBack { Button(role: .destructive) { act(.back) } label: { Label("Für alle zurücknehmen", systemImage: "arrow.uturn.backward") } }
    }

    private var sysLine: String {
        let who = l.mine ? String(localized: "Du") : l.name.isEmpty ? String(localized: "Jemand") : l.name
        let people = l.who.joined(separator: ", ")
        switch l.sys {
        case "joined": return l.mine ? String(localized: "Du bist mit einer Einladung dazugekommen") : who + " " + String(localized: "ist mit deiner Einladung dazugekommen")
        case "leave": return who + " " + String(localized: "hat die Gruppe verlassen")
        case "made": return who + " " + String(localized: "hat die Gruppe erstellt")
        case "add": return who + " " + String(localized: "fügte hinzu:") + " " + people
        case "remove": return who + " " + String(localized: "nahm heraus:") + " " + people
        case "admin": return who + " " + String(localized: "machte zum Admin:") + " " + people
        case "name": return who + " " + String(localized: "nannte die Gruppe") + " „" + l.text + "“"
        case "vanish":
            return who + " " + (l.secs > 0 ? String(localized: "stellte ein: Nachrichten verschwinden") + " " + ChatChoice.vanishText(l.secs)
                                           : String(localized: "schaltete „Nachrichten verschwinden“ aus"))
        case "newkey": return who + " " + String(localized: "hat ein Gerät für private Chats eingetragen")
        case "keygone": return who + " " + String(localized: "hat ein Gerät aus den privaten Chats genommen")
        case "call":
            let d = l.secs > 0 ? String(format: " · %d:%02d", l.secs / 60, l.secs % 60) : ""
            return (l.video ? "🎥 " + String(localized: "Videoanruf") : "📞 " + String(localized: "Anruf")) + d
        case "call_rejected":
            return l.video ? "🎥 " + String(localized: "Videoanruf abgelehnt") : "📞 " + String(localized: "Anruf abgelehnt")
        case "call_missed":
            if l.mine { return l.video ? "🎥 " + String(localized: "Videoanruf nicht angenommen") : "📞 " + String(localized: "Anruf nicht angenommen") }
            return l.video ? "🎥 " + String(localized: "Verpasster Videoanruf") : "📞 " + String(localized: "Verpasster Anruf")
        default: return String(localized: "Änderung im Chat")
        }
    }
}

private struct ChatPhoto: View {
    let chat: String
    let l: ChatLine
    @State private var thumb: UIImage?
    @State private var big: UIImage?
    @State private var showing = false

    var body: some View {
        let w = CGFloat(max(l.media?.w ?? 4, 1)), h = CGFloat(max(l.media?.h ?? 3, 1))
        Button {
            showing = true
            Task {
                if big == nil, let d = try? await ChatMediaLoad.data(chat, l) { big = UIImage(data: d) }
            }
        } label: {
            Group {
                if let thumb { Image(uiImage: thumb).resizable().scaledToFit() } else { Color.gray.opacity(0.2) }
            }
            .frame(width: min(220, 220 * w / max(w, h)), height: min(220, 220 * h / max(w, h)))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Foto groß zeigen")
        .task {
            if thumb == nil, let d = try? await ChatMediaLoad.data(chat, l, part: "t") { thumb = UIImage(data: d) }
        }
        .fullScreenCover(isPresented: $showing) {
            ZStack(alignment: .topTrailing) {
                Color.black.ignoresSafeArea()
                if let img = big ?? thumb { Image(uiImage: img).resizable().scaledToFit().frame(maxWidth: .infinity, maxHeight: .infinity) }
                Button { showing = false } label: {
                    Image(systemName: "xmark.circle.fill").font(.largeTitle).foregroundStyle(.white.opacity(0.8)).padding()
                }
                .accessibilityLabel("Schließen")
            }
        }
    }
}

private struct ChatVoice: View {
    let chat: String
    let l: ChatLine
    @State private var player: AVAudioPlayer?
    @State private var playing = false
    @State private var failed = false

    var body: some View {
        Button {
            if playing { player?.stop(); playing = false; return }
            Task {
                // AAC from the Spark (chats.py keeps voice messages so that iPhones play them)
                if player == nil, let d = try? await ChatMediaLoad.data(chat, l) {
                    // a private one as the other device recorded it: the player finds the format itself
                    player = try? AVAudioPlayer(data: d, fileTypeHint: l.fileKey == nil ? "public.aac-audio" : nil)
                }
                guard let p = player else { failed = true; return }
                try? AVAudioSession.sharedInstance().setCategory(.playback)
                p.currentTime = 0
                playing = p.play()
                let secs = p.duration
                try? await Task.sleep(for: .seconds(secs + 0.3))
                playing = false
            }
        } label: {
            Label {
                Text(verbatim: String(format: "%d:%02d", (l.media?.secs ?? 0) / 60, (l.media?.secs ?? 0) % 60))
            } icon: {
                Image(systemName: playing ? "stop.circle.fill" : failed ? "exclamationmark.circle" : "play.circle.fill").font(.title2)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(playing ? Text("Anhalten") : Text("Sprachnachricht abspielen"))
    }
}

private struct ChatFile: View {
    let chat: String
    let l: ChatLine
    let f: ChatMedia
    @State private var url: URL?
    @State private var loading = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "doc.fill").font(.title2).foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text(verbatim: f.name.isEmpty ? String(localized: "Datei") : f.name).font(.subheadline.bold()).lineLimit(1)
                Text(verbatim: f.ext.uppercased() + " · " + ByteCountFormatter.string(fromByteCount: Int64(f.size), countStyle: .file))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let url {
                ShareLink(item: url) { Image(systemName: "square.and.arrow.up") }
            } else {
                Button {
                    Task { await fetch() }
                } label: {
                    if loading { ProgressView() } else { Image(systemName: "arrow.down.circle") }
                }
                .accessibilityLabel("Herunterladen")
            }
        }
    }

    /// Into the app's own temporary folder under a clean name (never a path from the name), then to share or save.
    private func fetch() async {
        guard SparkAPI.current != nil, !loading else { return }
        loading = true
        defer { loading = false }
        guard let d = try? await ChatMediaLoad.data(chat, l) else { return }
        let safe = f.name.components(separatedBy: CharacterSet(charactersIn: "/\\:")).joined(separator: "_")
        let target = FileManager.default.temporaryDirectory.appendingPathComponent(safe.isEmpty ? "Datei" : safe)
        if (try? d.write(to: target, options: .atomic)) != nil { url = target }
    }
}
