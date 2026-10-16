import AVFoundation
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

// Chats (app/panel/chats.py, plan messenger.md): writing with the other people of this Spark like in a messenger.
// The list of chats, one chat with bubbles, ticks, photos, files and voice messages, a new chat with a person.
// Groups, invitations and the chat's settings stay in the browser. What others write is their text: it is only
// shown here, never acted on. Photos and voice come with this iPhone's key (never a link someone else could open).

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
    /// a call's line (anrufe.py): how long and whether with picture
    var secs = 0
    var video = false
}

struct ChatState {
    var enabled = false
    var on = false
    var media = false
    var chats: [ChatSummary] = []
    var contacts: [Recipient] = []
    var maxText = 4000
    /// Takes part in the fixed group "Alle" (Nachricht an alle).
    var all = false
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
        s.maxText = (d["max_text"] as? NSNumber)?.intValue ?? 4000
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

    /// (title, lines, may write, why not)
    func chatItems(_ id: String) async throws -> (String, [ChatLine], Bool, String) {
        var c = URLComponents(url: base.appendingPathComponent("api/chats/items"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: id)]
        var r = request("api/chats/items")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        let lines: [ChatLine] = (d["items"] as? [[String: Any]] ?? []).compactMap { x in
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
            if l.kind == "box" && !l.gone {   // private chat (chatsec.py): end-to-end, this app has no key for it yet
                l.kind = "text"
                l.text = String(localized: "🔒 Private Nachricht. Lesbar im Browser oder in der Android-App, auf dem iPhone mit dem nächsten Build.")
            }
            if let m = x["media"] as? [String: Any] {
                l.media = ChatMedia(w: (m["w"] as? NSNumber)?.intValue ?? 0, h: (m["h"] as? NSNumber)?.intValue ?? 0,
                                    secs: (m["secs"] as? NSNumber)?.intValue ?? 0, size: (m["size"] as? NSNumber)?.intValue ?? 0,
                                    ext: String((m["ext"] as? String ?? "").prefix(8)), name: String((m["name"] as? String ?? "").prefix(120)))
            }
            return l
        }
        if d["private"] as? Bool == true {
            return ("🔒 " + String((d["title"] as? String ?? "").prefix(60)), lines, false,
                    String(localized: "Private Chats schreibst du im Browser oder in der Android-App; auf dem iPhone mit dem nächsten Build."))
        }
        return (String((d["title"] as? String ?? "").prefix(60)), lines, d["can_send"] as? Bool ?? false,
                String((d["why"] as? String ?? "").prefix(200)))
    }

    func chatOpen(to: String) async throws -> String {
        try await post("api/chats/open", ["to": to])["id"] as? String ?? ""
    }

    func chatSend(_ id: String, text: String) async throws {
        _ = try await post("api/chats/send", ["id": id, "text": text])
    }

    func chatRead(_ id: String) async throws {
        _ = try await post("api/chats/read", ["id": id])
    }

    /// A photo (JPEG), file or recorded voice message as the raw body; a file's name in a header, never in the address.
    func chatMedia(_ id: String, kind: String, data: Data, name: String = "") async throws {
        var c = URLComponents(url: base.appendingPathComponent("api/chats/media"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: id), URLQueryItem(name: "kind", value: kind)]
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

// ---------------------------------------------------------------- the list
@MainActor
final class ChatsModel: ObservableObject {
    @Published var state = ChatState()
    @Published var loading = true
    @Published var error: String?

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
}

struct ChatsView: View {
    @StateObject private var m = ChatsModel()
    @Environment(\.dismiss) private var dismiss
    @State private var path: [String] = []
    @State private var picking = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if m.loading {
                    ProgressView()
                } else if !m.state.on {
                    Text(SparkAPI.way(m.state.enabled
                        ? String(localized: "Chats hat der Admin für dich gesperrt.")
                        : String(localized: "Chats sind auf dem Spark aus. Der Admin schaltet sie unter Funktionen → Chats ein.")))
                } else if m.state.chats.isEmpty {
                    Text("Noch keine Chats. Mit ＋ schreibst du jemandem.").foregroundStyle(.secondary)
                } else {
                    ForEach(m.state.chats) { c in
                        NavigationLink(value: c.id) { ChatRow(c: c) }
                    }
                }
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .navigationTitle("Chats")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: String.self) { id in
                let c = m.state.chats.first { $0.id == id }
                // calls only in a chat of two on this Spark (anrufe.py); "new chat" opens one of two as well
                ChatThreadView(id: id, title: c?.title ?? "", media: m.state.media, maxText: m.state.maxText,
                               callable: Conversation.shared.allowed.calls && !(c?.group ?? false) && !(c?.far ?? false))
            }
            .refreshable { await m.load() }
            .task {
                // the list stays fresh while it is open (the page in the browser has a live connection instead)
                while !Task.isCancelled {
                    await m.load()
                    try? await Task.sleep(for: .seconds(15))
                }
            }
            .onChange(of: path) { if path.isEmpty { Task { await m.load() } } }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
                if m.state.on {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { picking = true } label: { Image(systemName: "square.and.pencil") }
                            .accessibilityLabel("Neuer Chat")
                    }
                }
            }
            .sheet(isPresented: $picking) {
                NavigationStack {
                    List {
                        if m.state.contacts.isEmpty {
                            Text(SparkAPI.way(String(localized: "Niemand nimmt gerade Nachrichten von dir an. Jede Person legt unter Ich → Gespräch → Chats fest, wer ihr schreiben darf.")))
                                .foregroundStyle(.secondary)
                        }
                        ForEach(m.state.contacts) { p in
                            Button(p.name) {
                                Task {
                                    guard let api = SparkAPI.current else { return }
                                    do {
                                        let id = try await api.chatOpen(to: p.id)
                                        picking = false
                                        await m.load()
                                        path = [id]
                                    } catch {
                                        m.error = error.localizedDescription
                                        picking = false
                                    }
                                }
                            }
                        }
                    }
                    .navigationTitle("Neuer Chat")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { picking = false } } }
                }
                .presentationDetents([.medium, .large])
            }
        }
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

// ---------------------------------------------------------------- one chat
@MainActor
final class ChatThreadModel: ObservableObject {
    let id: String
    @Published var title: String
    @Published var lines: [ChatLine] = []
    @Published var canSend = false
    @Published var why = ""
    @Published var text = ""
    @Published var busy = false
    @Published var error: String?

    init(id: String, title: String) {
        self.id = id
        self.title = title
    }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let (t, l, may, w) = try await api.chatItems(id)
            if !t.isEmpty { title = t }
            if l != lines { lines = l }
            canSend = may
            why = w
            error = nil
            try? await api.chatRead(id)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func send(max: Int) async {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let api = SparkAPI.current, !t.isEmpty, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            try await api.chatSend(id, text: String(t.prefix(max)))
            text = ""
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func sendPhoto(_ item: PhotosPickerItem) async {
        guard let api = SparkAPI.current, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            // the Spark saves it anew without place data; JPEG here so HEIC from the camera fits too
            guard let raw = try await item.loadTransferable(type: Data.self), let image = UIImage(data: raw),
                  let jpeg = image.jpegData(compressionQuality: 0.85) else {
                throw SparkError(message: String(localized: "Das Foto kann ich nicht laden."))
            }
            try await api.chatMedia(id, kind: "photo", data: jpeg)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func sendFile(_ url: URL) async {
        guard let api = SparkAPI.current, !busy else { return }
        busy = true
        defer { busy = false }
        let open = url.startAccessingSecurityScopedResource()
        defer { if open { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            try await api.chatMedia(id, kind: "file", data: data, name: url.lastPathComponent)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct ChatThreadView: View {
    @StateObject private var m: ChatThreadModel
    let media: Bool
    let maxText: Int
    @State private var photo: PhotosPickerItem?
    @State private var files = false
    @FocusState private var writing: Bool

    let callable: Bool
    @ObservedObject private var calls = CallCenter.shared

    init(id: String, title: String, media: Bool, maxText: Int, callable: Bool = false) {
        _m = StateObject(wrappedValue: ChatThreadModel(id: id, title: title))
        self.media = media
        self.maxText = maxText
        self.callable = callable
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 6) {
                        if m.lines.isEmpty {
                            Text("Schreib die erste Nachricht.").font(.footnote).foregroundStyle(.secondary).padding(.top, 20)
                        }
                        ForEach(m.lines) { l in
                            ChatBubble(chat: m.id, l: l).id(l.id)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: m.lines.last?.id) { _, last in
                    if let last { withAnimation { proxy.scrollTo(last, anchor: .bottom) } }
                }
                .onAppear { if let last = m.lines.last?.id { proxy.scrollTo(last, anchor: .bottom) } }
            }
            if let e = m.error {
                Text(SparkAPI.way(e)).font(.footnote).foregroundStyle(.red).padding(.horizontal).padding(.vertical, 4)
            }
            if m.canSend { composer } else if !m.why.isEmpty {
                Text(verbatim: m.why).font(.footnote).foregroundStyle(.secondary).padding()
            }
        }
        .navigationTitle(Text(verbatim: m.title))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if callable {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { calls.dial(chat: m.id, name: m.title, video: false) } label: { Image(systemName: "phone") }
                        .accessibilityLabel("Anrufen").disabled(calls.active)
                    Button { calls.dial(chat: m.id, name: m.title, video: true) } label: { Image(systemName: "video") }
                        .accessibilityLabel("Videoanruf").disabled(calls.active)
                }
            }
        }
        .task {
            while !Task.isCancelled {   // fresh while the chat is open
                await m.load()
                try? await Task.sleep(for: .seconds(4))
            }
        }
        .onChange(of: photo) {
            guard let item = photo else { return }
            photo = nil
            Task { await m.sendPhoto(item) }
        }
        .fileImporter(isPresented: $files, allowedContentTypes: [.pdf, .plainText, .commaSeparatedText, .data]) { result in
            if case .success(let url) = result { Task { await m.sendFile(url) } }
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if media {
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
                .onChange(of: m.text) { _, t in if t.count > maxText { m.text = String(t.prefix(maxText)) } }
            Button {
                Task { await m.send(max: maxText) }
            } label: {
                if m.busy { ProgressView().frame(width: 36, height: 36) } else {
                    Image(systemName: "arrow.up.circle.fill").font(.system(size: 32))
                }
            }
            .accessibilityLabel("Senden")
            .disabled(m.busy || m.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(.bar)
    }
}

private struct ChatBubble: View {
    let chat: String
    let l: ChatLine

    var body: some View {
        if l.kind == "sys" {
            Text(verbatim: sysLine).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(.vertical, 2)
        } else {
            HStack {
                if l.mine { Spacer(minLength: 40) }
                VStack(alignment: .leading, spacing: 4) {
                    if !l.mine && !l.name.isEmpty {
                        Text(verbatim: l.name).font(.caption.bold()).foregroundStyle(.secondary)
                    }
                    if l.gone {
                        Text(l.mine ? LocalizedStringKey("Du hast diese Nachricht zurückgenommen.") : LocalizedStringKey("Diese Nachricht wurde zurückgenommen."))
                            .italic().foregroundStyle(.secondary)
                    } else {
                        if l.kind == "photo" { ChatPhoto(chat: chat, l: l) }
                        if l.kind == "voice" { ChatVoice(chat: chat, l: l) }
                        if l.kind == "file", let f = l.media { ChatFile(chat: chat, mid: l.id, f: f) }
                        if !l.text.isEmpty {
                            Text(verbatim: l.text).italic(l.kind == "voice").textSelection(.enabled)
                        }
                    }
                    HStack(spacing: 4) {
                        if l.edited { Text("bearbeitet") }
                        Text(l.date, format: .dateTime.hour().minute())
                        if l.mine && !l.tick.isEmpty {
                            Text(verbatim: l.tick == "sent" ? "✓" : "✓✓").foregroundStyle(l.tick == "read" ? Color.blue : Color.secondary)
                        }
                    }
                    .font(.caption2).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(RoundedRectangle(cornerRadius: 16).fill(l.mine ? Color.accentColor.opacity(0.18) : Color(.secondarySystemBackground)))
                if !l.mine { Spacer(minLength: 40) }
            }
        }
    }

    private var sysLine: String {
        let who = l.mine ? String(localized: "Du") : l.name
        switch l.sys {
        case "joined": return l.mine ? String(localized: "Du bist mit einer Einladung dazugekommen") : who + " " + String(localized: "ist mit deiner Einladung dazugekommen")
        case "leave": return who + " " + String(localized: "hat die Gruppe verlassen")
        case "made": return who + " " + String(localized: "hat die Gruppe erstellt")
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
                if big == nil, let api = SparkAPI.current, let d = try? await api.chatMediaData(chat, mid: l.id) { big = UIImage(data: d) }
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
            if thumb == nil, let api = SparkAPI.current, let d = try? await api.chatMediaData(chat, mid: l.id, part: "t") { thumb = UIImage(data: d) }
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
                if player == nil, let api = SparkAPI.current, let d = try? await api.chatMediaData(chat, mid: l.id) {
                    player = try? AVAudioPlayer(data: d, fileTypeHint: "public.aac-audio")
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
    let mid: String
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
        guard let api = SparkAPI.current, !loading else { return }
        loading = true
        defer { loading = false }
        guard let d = try? await api.chatMediaData(chat, mid: mid) else { return }
        let safe = f.name.components(separatedBy: CharacterSet(charactersIn: "/\\:")).joined(separator: "_")
        let target = FileManager.default.temporaryDirectory.appendingPathComponent(safe.isEmpty ? "Datei" : safe)
        if (try? d.write(to: target, options: .atomic)) != nil { url = target }
    }
}
