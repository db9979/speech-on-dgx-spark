import Foundation
import UIKit

struct SparkError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// What the answer stream of /api/chat brings (Server-Sent Events, see app/panel/chat.py).
enum ChatEvent {
    case text(String)
    case drop(Int)          // the last characters were taken back
    case audio(Data)        // 16-bit PCM, 24 kHz, mono
    case mark(String)       // "mail", "outside" or "screen": the answer rests on text from outside
    case error(String)
    case reminderSet(Reminder)
    case reminderCancel([String])
    case action(kind: String, target: String)   // iphone_action: "navigate" or "call"
    case face(String)       // what the answer is doing, for the face: search, calendar, mail, home, memory, happy, error
    case rate(String)       // 👍/👎 may go under this answer (only when the profile's switch is on): its id
    case picture(job: String, prompt: String)   // a picture is painted for this answer (bilder.py): its job
    case more(kind: String, items: [MoreItem])  // the Spark's fixed sentences under the answer (saetze.py)
    case step(StepItem)     // Ablauf zeigen (ablauf.py): one tool of this answer, its readable name, ok and time
    case confirm(String)    // Freigabe-Karte (ablauf.py): the kind of a proposal waiting for "Ja", in fixed words
}

/// One tool of an answer (ablauf.py): only its readable name, whether it worked and its time, never what it found.
struct StepItem: Hashable {
    let name: String
    let ok: Bool
    let ms: Int
}

/// „Das kannst du auch sagen“ (saetze.py): a sentence the person can say, and the tool it is for (only its name
/// goes back when the sentence is sent as it was suggested).
struct MoreItem: Hashable {
    let text: String
    let tool: String
}

struct Reminder {
    let id: String
    let text: String
    let due: Date
}

/// Text read from a photo or a document on this iPhone (the Spark gets only the text).
struct Attachment: Equatable {
    let kind: String        // "photo" or "document"
    let name: String
    let text: String
    /// the photo itself (JPEG, at most 1280 px) when the Spark may look at pictures; then text is empty
    var image: Data? = nil
}

/// The Spark looks at a photo only for 10 minutes after the last question: the id of an uploaded
/// photo is used again within that time, after that (or on 410) the photo goes up again.
actor ImageIds {
    static let shared = ImageIds()
    private var known: [Data: (id: String, used: Date)] = [:]
    private let keep: TimeInterval = 540

    func id(for data: Data, upload: () async throws -> String) async throws -> String {
        if let k = known[data], Date().timeIntervalSince(k.used) < keep { return k.id }
        let id = try await upload()
        known = known.filter { Date().timeIntervalSince($0.value.used) < keep }
        known[data] = (id, Date())
        return id
    }

    func used(_ data: Data) {
        if let k = known[data] { known[data] = (k.id, Date()) }
    }

    func forget(_ data: Data) {
        known[data] = nil
    }
}

/// The Spark does not look at pictures for this profile (403) or not at this one (415): read the text instead.
struct ImagesOff: Error {}

/// A conversation from the profile's list (the same list as the panel's Protokoll).
struct SavedConvo: Identifiable {
    let id: String
    let title: String
    let updated: Date
    let msgs: [[String: Any]]
}

struct Note {
    let id: String
    let t: Int
    let text: String
    let mail: Bool
}

/// What the profile allows the app (from /api/iphone/hello; the panel decides).
struct Allowed: Equatable {
    var profile = ""
    var language = "auto"
    var listen = false
    var act = false
    var proactive = false
    var reminders = true
    var face = "robot"
    /// "Gesicht zeigt, was es tut" (admin switch chat.face_life, V01.0.294)
    var faceLife = false
    var push = false
    var carHa = false
    var docs = false
    var ios = false
    /// the app may send photos for the Spark to look at (admin, profile and app switch)
    var images = false
    /// Spark updates (rights only from the admin): notices and the version page, starting the update
    var updateNotify = false
    var updateStart = false
    /// the app may show where the profile's devices listen in room mode and end it (admin room mode, profile switch app_room)
    var rooms = false
    /// panel areas in the app (admin switch chat.iphone_panel): "Im Panel öffnen" and the areas the profile switched on
    var panel = false
    var areas: Set<String> = []
    /// the profile's own admin role while it counts ("admin" or "manager", V01.0.541): "Spark verwalten" in the app
    var adminRole = ""
    /// "Problem melden" (meldung.py): admin switch chat.report, not blocked for this profile
    var report = false
    /// "Vom Spark erstellt" (docmake.py): admin switch chat.doc_make, not blocked for this profile
    var make = false
    /// Anrufe (anrufe.py): voice and video in a chat of two, ringing through CallKit (Calls.swift)
    var calls = false
}

/// A device of the profile in room mode (from /api/room/active): only where and until when, never what was heard.
struct ListeningRoom: Identifiable, Equatable, Hashable, Codable {
    let id: String          // the room's public key on the Spark (for "Beenden")
    let name: String
    let kind: String        // "browser" or "speaker"
    let until: Date
}

extension ListeningRoom {
    init?(_ d: [String: Any]) {
        guard let key = d["key"] as? String, !key.isEmpty, key.count <= 40,
              let until = (d["until"] as? NSNumber)?.doubleValue else { return nil }
        self.init(id: key, name: String((d["name"] as? String ?? "").prefix(40)),
                  kind: d["kind"] as? String ?? "", until: Date(timeIntervalSince1970: until / 1000))
    }
}

/// What /api/iphone/update says: the installed and the newest tested version, a running update.
struct UpdateState {
    var installed = ""
    var latest: String?
    var newer = false
    var changes: [String] = []
    var error: String?
    var running = false
    var percent = 0
    var step = ""
    var done = false
    var ok: Bool?
    var start = false
    var wait = 0
}

struct Recipient: Identifiable, Hashable {
    let id: String
    let name: String
    /// The Rufname ("Tom", "Papa") others may use for this profile; "" when there is none.
    var call = ""

    var label: String { call.isEmpty ? name : "\(name) (\(call))" }
}

/// One of the profile's documents (GET /api/profile/docs).
struct SparkDoc: Identifiable, Equatable {
    let id: String
    let name: String
    let kind: String        // text, scan, picture
    let state: String       // ready, reading, ...
    let file: Bool          // the original is kept on the Spark
    let size: Int
    let created: Date
    let pages: Int
    let todo: Int
    /// "Dokumente verwalten": searchable, "Für alle", the Steckbrief's title, deadline and tags
    var use = true
    var shared = false
    var title = ""
    var due = ""
    var tags: [String] = []
    /// "nas": read from a knowledge folder (Synology S8); place is its folder there, the file is fetched when opened
    var source = ""
    var place = ""
    /// the Steckbrief: what kind of paper, from whom, and its short summary
    var art = ""
    var sender = ""
    var brief = ""
    /// why it could not be read (state "error"), a fixed sentence of the Spark
    var note = ""
    /// the title of the Steckbrief, else the file name
    var shown: String { title.isEmpty ? name : title }
}

/// A document the Spark made (GET /api/make): its newest version and the small preview of the first part.
struct MadeDoc: Identifiable, Equatable {
    let id: String
    let title: String
    let kind: String        // praesentation, brief, tabelle, ...
    let format: String      // docx, pptx, xlsx, pdf, md, txt, csv
    let style: String
    let updated: Date
    let version: Int
    var heading = ""
    var lines: [String] = []
    var rows: [[String]] = []
    var parts = 0

    static let formatNames = ["docx": "Word", "pptx": "PowerPoint", "xlsx": "Excel", "pdf": "PDF", "md": "Markdown",
                              "txt": "Text", "csv": "CSV"]
    var formatName: String { Self.formatNames[format] ?? format }
}

/// What a document says, as the Spark stored it.
struct DocText {
    var name = ""
    var parts: [(page: Int?, text: String)] = []
    var cut = false
    /// Where the next part starts ("Weiterlesen"), nil when everything is here.
    var next: Int?
}

/// The Spark's panel, spoken to with this iPhone's own device key. The key may only ask and
/// listen (chat, speech recognition, the Siri question, hello); the panel refuses everything else.
struct SparkAPI {
    let base: URL
    let key: String?

    static var current: SparkAPI? {
        guard let base = Store.baseURL, let key = Store.key else { return nil }
        return SparkAPI(base: base, key: key)
    }

    func request(_ path: String, method: String = "GET") -> URLRequest {
        var r = URLRequest(url: base.appendingPathComponent(path))
        r.httpMethod = method
        r.timeoutInterval = 120
        if let key { r.setValue(key, forHTTPHeaderField: "X-Speech-Device") }
        return r
    }

    static func check(_ data: Data, _ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { throw SparkError(message: String(localized: "Keine Antwort vom Spark.")) }
        guard !(200..<300).contains(http.statusCode) else { return }
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        let detail = json?["detail"] as? String
        switch http.statusCode {
        case 401:
            throw SparkError(message: String(localized: "Der Spark nimmt dieses iPhone nicht an. Im Panel unter Ich → iPhone-App prüfen, ob die App an ist, sonst neu koppeln."))
        case 413:
            throw SparkError(message: String(localized: "Das Foto ist zu groß für den Spark."))
        case 428:
            throw SparkError(message: String(localized: "Der Code stimmt nicht. Bitte den aktuellen Code aus der Authenticator-App nehmen."))
        case 429 where (detail ?? "").hasPrefix("Das Update"):   // one start from the app per 10 minutes
            throw SparkError(message: detail ?? "")
        case 429:
            throw SparkError(message: String(localized: "Der Spark ist gerade ausgelastet. Bitte gleich noch einmal."))
        case 503 where json?["notaus"] != nil:
            // the Notaus holds the Spark or this profile off (notaus.py); lifting is never possible from the app
            if (detail ?? "").hasPrefix("Mein Notaus") {
                throw SparkError(message: String(localized: "Mein Notaus ist an. Aufheben im Browser unter Ich → Sicherheit mit der PIN."))
            }
            let level = (json?["notaus"] as? NSNumber)?.intValue ?? 0
            throw SparkError(message: String(localized: "Der Notaus ist an (Stufe \(level)). Aufheben kann nur ein Admin im Browser."))
        case 503 where (detail ?? "").hasPrefix("Für dieses Gerät") || (detail ?? "").hasPrefix("Mein Notaus"):
            // switched off for this profile right now (Gesperrte Funktionen) or Mein Notaus: the pairing stays (V01.0.388)
            throw SparkError(message: detail ?? "")
        case 503:
            throw SparkError(message: String(localized: "Die Spracherkennung oder das Sprachmodell läuft gerade nicht."))
        default:
            throw SparkError(message: detail ?? String(localized: "Fehler \(http.statusCode) vom Spark."))
        }
    }

    /// the faces the app can draw (core.FACES); anything else stays the robot
    static func knownFace(_ v: Any?) -> String {
        let f = v as? String ?? ""
        return ["comic", "comic_woman"].contains(f) ? f : "robot"
    }

    static func object(_ data: Data) -> [String: Any] {
        (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func post(_ path: String, _ body: [String: Any]) async throws -> [String: Any] {
        var r = request(path, method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return Self.object(data)
    }

    /// The one-time code from the pairing link gives this iPhone its own key.
    static func pair(base: URL, code: String, name: String) async throws -> (key: String, profile: String, language: String) {
        let d = try await SparkAPI(base: base, key: nil).post("api/iphone/pair", ["code": code, "name": name])
        guard let key = d["token"] as? String, !key.isEmpty else {
            throw SparkError(message: String(localized: "Der Spark hat keinen Schlüssel geschickt."))
        }
        return (key, d["profile"] as? String ?? "", d["language"] as? String ?? "auto")
    }

    /// What an invitation offers before it is used: the suggested name and how long the PIN must be.
    static func invitation(base: URL, code: String) async throws -> (name: String, pinMin: Int, pinOnly: Bool) {
        let d = try await SparkAPI(base: base, key: nil).post("api/join/check", ["code": code])
        return (d["name"] as? String ?? "", max(4, min(d["pin_min"] as? Int ?? 6, 32)), d["kind"] as? String == "pin")
    }

    /// An invitation makes the profile and gives this iPhone its key in one step (api/iphone/join).
    static func join(base: URL, code: String, name: String, pin: String, device: String) async throws -> (key: String, profile: String, language: String) {
        let d = try await SparkAPI(base: base, key: nil).post("api/iphone/join", ["code": code, "name": name, "pin": pin, "device": device])
        guard let key = d["token"] as? String, !key.isEmpty else {
            throw SparkError(message: String(localized: "Der Spark hat keinen Schlüssel geschickt."))
        }
        return (key, d["profile"] as? String ?? "", d["language"] as? String ?? "auto")
    }

    /// Checks the key: whose it is and what the profile allows the app.
    func hello(timeout: TimeInterval = 120) async throws -> Allowed {
        var r = request("api/iphone/hello")
        r.timeoutInterval = timeout
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        return Allowed(profile: d["profile"] as? String ?? "", language: d["language"] as? String ?? "auto",
                       listen: d["listen"] as? Bool ?? false, act: d["act"] as? Bool ?? false,
                       proactive: d["proactive"] as? Bool ?? false, reminders: d["reminders"] as? Bool ?? true,
                       face: Self.knownFace(d["face"]),
                       faceLife: d["face_life"] as? Bool ?? false,
                       push: d["push"] as? Bool ?? false, carHa: d["car_ha"] as? Bool ?? false,
                       docs: d["docs"] as? Bool ?? false, ios: d["ios"] as? Bool ?? false,
                       images: d["images"] as? Bool ?? false,
                       updateNotify: (d["update"] as? [String: Any])?["notify"] as? Bool ?? false,
                       updateStart: (d["update"] as? [String: Any])?["start"] as? Bool ?? false,
                       rooms: d["rooms"] as? Bool ?? false,
                       panel: d["panel"] as? Bool ?? false,
                       areas: Set(((d["areas"] as? [String: Any]) ?? [:]).compactMap { $0.value as? Bool == true ? $0.key : nil }),
                       adminRole: ["admin", "manager"].contains(d["admin_role"] as? String ?? "") ? d["admin_role"] as? String ?? "" : "",
                       report: d["report"] as? Bool ?? false, make: d["make"] as? Bool ?? false,
                       calls: d["calls"] as? Bool ?? false)
    }

    /// Where the profile's devices listen in room mode right now (names and end times only).
    func rooms() async throws -> [ListeningRoom] {
        var r = request("api/room/active")
        r.timeoutInterval = 15
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let list = Self.object(data)["rooms"] as? [[String: Any]] ?? []
        return list.prefix(50).compactMap { ListeningRoom($0) }
    }

    /// Ends one room (its key) or, without a key, all rooms of the profile. Starting is not possible from the app.
    func endRoom(_ key: String? = nil) async throws {
        var body: [String: Any] = ["all": true]
        if let key { body = ["key": key] }
        _ = try await post("api/room/end", body)
    }

    static func reminder(_ d: [String: Any]) -> Reminder? {
        guard let id = d["id"] as? String, let due = (d["due"] as? NSNumber)?.doubleValue else { return nil }
        return Reminder(id: id, text: d["text"] as? String ?? "Erinnerung", due: Date(timeIntervalSince1970: due / 1000))
    }

    /// The profile's pending timers and reminders (the iPhone rings for them).
    func reminders() async throws -> [Reminder] {
        let (data, response) = try await URLSession.shared.data(for: request("api/profile/reminders"))
        try Self.check(data, response)
        let list = (try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]) ?? []
        return list.compactMap(Self.reminder)
    }

    /// A due reminder rings on one device only: true when this device is the first to play it.
    /// Without an answer from the Spark it rings anyway (rather once too often than never).
    func played(_ id: String) async -> Bool {
        guard let d = try? await post("api/profile/reminders/played", ["id": id]) else { return true }
        return d["play"] as? Bool ?? true
    }

    /// Notes the Spark wants to say by itself ("Von selbst") since a time (ms).
    func notes(since: Int) async throws -> [Note] {
        var c = URLComponents(url: base.appendingPathComponent("api/proactive"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "since", value: String(since))]
        var r = request("api/proactive")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let items = Self.object(data)["items"] as? [[String: Any]] ?? []
        return items.compactMap { d in
            guard let id = d["id"] as? String, let text = d["text"] as? String else { return nil }
            return Note(id: id, t: (d["t"] as? NSNumber)?.intValue ?? 0, text: text, mail: d["mail"] as? Bool ?? false)
        }
    }

    /// A note is said on one device only: true when this device is the first to play it.
    func notePlayed(_ id: String) async -> Bool {
        guard let d = try? await post("api/proactive/played", ["id": id]) else { return true }
        return d["play"] as? Bool ?? true
    }

    /// A greeting when the app opens after a while (the Spark decides whether it says one).
    func greet() async throws -> Note? {
        let d = try await post("api/proactive/greet", [:])
        guard let item = d["item"] as? [String: Any], let id = item["id"] as? String, let text = item["text"] as? String else { return nil }
        return Note(id: id, t: (item["t"] as? NSNumber)?.intValue ?? 0, text: text, mail: false)
    }

    /// A text in the Spark voice (reminders, notes): 24 kHz PCM pieces.
    func say(_ text: String) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var r = request("api/assistant/say", method: "POST")
                    r.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    r.httpBody = try JSONSerialization.data(withJSONObject: ["text": String(text.prefix(1000))])
                    let (bytes, response) = try await URLSession.shared.bytes(for: r)
                    if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        try Self.check(Data(), response)
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data:") else { continue }
                        let ev = Self.object(Data(line.dropFirst(5).utf8))
                        if ev["type"] as? String == "audio", let s = ev["audio"] as? String, let pcm = Data(base64Encoded: s) {
                            cont.yield(pcm)
                        }
                    }
                    cont.finish()
                } catch {
                    cont.finish(throwing: error)
                }
            }
            cont.onTermination = { _ in task.cancel() }
        }
    }

    /// The recorded question (WAV) as text.
    /// opened: how the microphone opened by itself ("barge", "hands"); the Spark then takes only a known voice.
    func transcribe(wav: Data, language: String, opened: String = "") async throws -> String {
        let boundary = "spark-" + UUID().uuidString
        var r = request("api/test/asr", method: "POST")
        r.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n\(language)\r\n".utf8))
        if !opened.isEmpty {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"opened\"\r\n\r\n\(opened)\r\n".utf8))
        }
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"frage.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8))
        body.append(wav)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        r.httpBody = body
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return (Self.object(data)["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// A question for Siri: the answer as text (the Spark keeps follow-ups for ten minutes).
    func ask(_ text: String) async throws -> String {
        let d = try await post("api/siri/ask", ["text": text, "tz": TimeZone.current.identifier])
        return d["answer"] as? String ?? ""
    }

    /// The profile's conversations, newest first.
    func convos() async throws -> [SavedConvo] {
        let (data, response) = try await URLSession.shared.data(for: request("api/profile/convos"))
        try Self.check(data, response)
        let list = (try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]) ?? []
        return list.compactMap { d in
            guard let id = d["id"] as? String, let msgs = d["msgs"] as? [[String: Any]], !msgs.isEmpty else { return nil }
            let ms = (d["updated"] as? NSNumber)?.doubleValue ?? 0
            return SavedConvo(id: id, title: d["title"] as? String ?? "", updated: Date(timeIntervalSince1970: ms / 1000), msgs: msgs)
        }
    }

    /// What changed in the profile's conversations since a time (ms, the Spark's own clock), and which ones still
    /// exist (a conversation deleted on another device is missing from ids).
    func convos(since: Int) async throws -> (items: [SavedConvo], ids: Set<String>) {
        var c = URLComponents(url: base.appendingPathComponent("api/profile/convos"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "since", value: String(max(0, since)))]
        var r = request("api/profile/convos")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        let ids = Set((d["ids"] as? [String] ?? []).prefix(200))
        let list = d["items"] as? [[String: Any]] ?? []
        let items: [SavedConvo] = list.compactMap { x in
            guard let id = x["id"] as? String, let msgs = x["msgs"] as? [[String: Any]] else { return nil }
            let ms = (x["updated"] as? NSNumber)?.doubleValue ?? 0
            return SavedConvo(id: id, title: x["title"] as? String ?? "", updated: Date(timeIntervalSince1970: ms / 1000), msgs: msgs)
        }
        return (items, ids)
    }

    /// Adds new messages to one conversation in the profile's list (made if new; what another device added stays).
    /// "add" instead of "msgs": an older Spark refuses it rather than replacing the conversation.
    func saveConvo(id: String, title: String, msgs: [[String: Any]]) async throws {
        var r = request("api/profile/convos", method: "PUT")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: [
            "id": id, "title": String(title.prefix(80)), "add": msgs] as [String: Any])
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
    }

    // ---------------------------------------------------------------- looking at the own documents
    /// The profile's documents (only while Eigene Dokumente is released for the profile); nil when it is not.
    func docs() async throws -> [SparkDoc]? {
        let (data, response) = try await URLSession.shared.data(for: request("api/profile/docs"))
        if [401, 403].contains((response as? HTTPURLResponse)?.statusCode ?? 0) { return nil }
        try Self.check(data, response)
        let list = (try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]) ?? []
        return list.compactMap { d in
            guard let id = d["id"] as? String, Self.docId(id) else { return nil }
            return SparkDoc(id: id, name: String((d["name"] as? String ?? "").prefix(200)), kind: d["kind"] as? String ?? "text",
                            state: d["state"] as? String ?? "ready", file: d["file"] as? Bool ?? false,
                            size: (d["size"] as? NSNumber)?.intValue ?? 0,
                            created: Date(timeIntervalSince1970: (d["created"] as? NSNumber)?.doubleValue ?? 0),
                            pages: (d["pages"] as? NSNumber)?.intValue ?? 0, todo: (d["todo"] as? NSNumber)?.intValue ?? 0,
                            use: d["use"] as? Bool ?? true, shared: d["shared"] as? Bool ?? false,
                            title: String((d["title"] as? String ?? "").prefix(200)), due: String((d["due"] as? String ?? "").prefix(10)),
                            tags: (d["tags"] as? [String] ?? []).prefix(12).map { String($0.prefix(24)) },
                            source: String((d["source"] as? String ?? "").prefix(12)), place: String((d["place"] as? String ?? "").prefix(300)),
                            art: String((d["art"] as? String ?? "").prefix(60)), sender: String((d["sender"] as? String ?? "").prefix(80)),
                            brief: String((d["brief"] as? String ?? "").prefix(600)), note: String((d["note"] as? String ?? "").prefix(200)))
        }
    }

    private static func docId(_ id: String) -> Bool {
        id.range(of: "^[0-9a-f]{12}$", options: .regularExpression) != nil
    }

    func docText(_ id: String, start: Int = 0) async throws -> DocText {
        guard Self.docId(id) else { throw SparkError(message: String(localized: "Das Dokument gibt es nicht.")) }
        var r = request("api/profile/wissen/\(id)/text")
        if start > 0 {
            var c = URLComponents(url: base.appendingPathComponent("api/profile/wissen/\(id)/text"), resolvingAgainstBaseURL: false)!
            c.queryItems = [URLQueryItem(name: "start", value: String(min(start, 1_000_000)))]
            r.url = c.url
        }
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        var t = DocText()
        t.name = d["name"] as? String ?? ""
        t.parts = (d["parts"] as? [[String: Any]] ?? []).map { p in ((p["page"] as? NSNumber)?.intValue, p["text"] as? String ?? "") }
        t.cut = d["cut"] as? Bool ?? false
        t.next = t.cut ? (d["next"] as? NSNumber)?.intValue : nil
        return t
    }

    /// The kept original, only when it is a PDF or a picture (the Spark sends nothing else for looking at).
    /// Written to a file of its own in the app's temporary folder; the caller deletes it.
    func docOriginal(_ id: String) async throws -> URL? {
        guard Self.docId(id) else { return nil }
        var c = URLComponents(url: base.appendingPathComponent("api/profile/wissen/\(id)/file"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "view", value: "1")]
        var r = request("api/profile/wissen/\(id)/file")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        if (response as? HTTPURLResponse)?.statusCode == 404 { return nil }
        try Self.check(data, response)
        let type = ((response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
        let ext: String
        if type.hasPrefix("application/pdf") && data.starts(with: Data("%PDF".utf8)) { ext = "pdf" }
        else if type.hasPrefix("image/jpeg") && data.starts(with: Data([0xFF, 0xD8, 0xFF])) { ext = "jpg" }
        else { return nil }
        guard data.count <= 40 * 1024 * 1024 else { return nil }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("docs", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(id).\(ext)")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }

    // ---------------------------------------------------------------- pictures painted for an answer (bilder.py)
    static func isJob(_ s: String) -> Bool { s.count == 12 && s.allSatisfy { $0.isHexDigit && !$0.isUppercase } }

    /// A painted picture's job: "wait", "run", "done" (then the picture's id) or "error" (then the reason).
    func pictureJob(_ job: String) async throws -> (state: String, pic: String?, error: String) {
        let (data, response) = try await URLSession.shared.data(for: request("api/bilder/job/\(job)"))
        try Self.check(data, response)
        let d = Self.object(data)
        let pic = (d["pic"] as? [String: Any])?["id"] as? String
        return (d["state"] as? String ?? "", pic.flatMap { Self.isJob($0) ? $0 : nil }, d["error"] as? String ?? "")
    }

    /// The picture itself (PNG, only of the own profile).
    func pictureFile(_ id: String) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request("api/bilder/\(id)/datei"))
        try Self.check(data, response)
        return data
    }

    // ---------------------------------------------------------------- documents the Spark made (docmake.py)
    /// The made documents, newest first; nil when "Dokumente erstellen" is off for the profile.
    func madeDocs() async throws -> [MadeDoc]? {
        let (data, response) = try await URLSession.shared.data(for: request("api/make"))
        if [401, 403].contains((response as? HTTPURLResponse)?.statusCode ?? 0) { return nil }
        try Self.check(data, response)
        let list = (Self.object(data)["docs"] as? [[String: Any]]) ?? []
        // every text is the model's or the person's: shown as plain text only (Text(verbatim:)), cut to size
        func cut(_ v: Any?, _ n: Int) -> String { String((v as? String ?? "").prefix(n)) }
        return list.compactMap { d in
            guard let id = d["id"] as? String, Self.docId(id) else { return nil }
            let p = d["peek"] as? [String: Any] ?? [:]
            return MadeDoc(id: id, title: cut(d["title"], 200), kind: cut(d["kind"], 20), format: cut(d["format"], 8),
                           style: cut(d["style"], 20),
                           updated: Date(timeIntervalSince1970: (d["updated"] as? NSNumber)?.doubleValue ?? 0),
                           version: (d["version"] as? NSNumber)?.intValue ?? 0, heading: cut(p["heading"], 100),
                           lines: (p["lines"] as? [String] ?? []).prefix(4).map { String($0.prefix(200)) },
                           rows: (p["rows"] as? [[String]] ?? []).prefix(4).map { $0.prefix(4).map { String($0.prefix(30)) } },
                           parts: (p["parts"] as? NSNumber)?.intValue ?? 0)
        }
    }

    /// A made document's file, written to the app's temporary folder under its own name (for Apple's viewer and
    /// "Teilen"); the caller deletes it. Only the formats the Spark builds, at most 25 MB.
    func madeFile(_ d: MadeDoc) async throws -> URL {
        guard Self.docId(d.id), MadeDoc.formatNames[d.format] != nil else { throw SparkError(message: String(localized: "Das Dokument gibt es nicht.")) }
        var r = request("api/make/doc/\(d.id)/file")
        r.timeoutInterval = 120
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        guard data.count <= 25 * 1024 * 1024 else { throw SparkError(message: String(localized: "Die Datei ist zu groß.")) }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("made-\(d.id)", isDirectory: true)
        try? FileManager.default.removeItem(at: dir)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var name = d.title.replacingOccurrences(of: "[/\\\\:?*\"<>|\\x{00}-\\x{1F}]", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        if name.isEmpty || name.hasPrefix(".") { name = "Dokument" }
        let url = dir.appendingPathComponent(String(name.prefix(80)) + "." + d.format)
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }

    /// A document's text into the profile's documents (only while Eigene Dokumente is released).
    func storeDoc(name: String, text: String) async throws {
        var r = request("api/iphone/doc", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.timeoutInterval = 120
        r.httpBody = try JSONSerialization.data(withJSONObject: ["name": String(name.prefix(100)), "text": text])
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
    }

    /// New entries of a Spark list ("einkauf", "aufgaben"); the Spark hands each one over once.
    /// When the Spark refused a list (switch off, list in CalDAV, update running), the app waits as long
    /// as its Retry-After says (at most an hour) before it asks for that list again.
    @MainActor private static var listPause: [String: Date] = [:]

    func takeList(_ list: String) async throws -> [String] {
        if let until = await Self.pausedUntil(list), until > Date() { return [] }
        var c = URLComponents(url: base.appendingPathComponent("api/tasks/inbox"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "list", value: list), URLQueryItem(name: "format", value: "json")]
        var r = request("api/tasks/inbox", method: "POST")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        if let http = response as? HTTPURLResponse, [403, 409, 423].contains(http.statusCode) {
            let secs = min(3600, max(30, Double(http.value(forHTTPHeaderField: "Retry-After") ?? "") ?? 300))
            await Self.pause(list, until: Date().addingTimeInterval(secs))
            return []
        }
        try Self.check(data, response)
        return (Self.object(data)["items"] as? [String] ?? []).filter { !$0.isEmpty }
    }

    @MainActor private static func pausedUntil(_ list: String) -> Date? { listPause[list] }
    @MainActor private static func pause(_ list: String, until: Date) { listPause[list] = until }

    /// Puts entries on a Spark list (from Shortcuts; comma or line separated).
    func addToList(_ list: String, _ text: String) async throws {
        _ = try await post("api/profile/tasks/" + list, ["text": String(text.prefix(2000))])
    }

    /// What is due today (today.py, the panel's Ich → Heute): cards of the functions the profile may use.
    func today() async throws -> [String: Any] {
        var r = request("api/profile/today")
        if let url = r.url, var c = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            c.queryItems = [URLQueryItem(name: "tz", value: TimeZone.current.identifier)]
            r.url = c.url
        }
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return Self.object(data)
    }

    /// The profile's own settings the app may show ("Mein Profil"; iphone.APP_FIELDS on the Spark).
    func profileSettings() async throws -> [String: Any] {
        let (data, response) = try await URLSession.shared.data(for: request("api/iphone/settings"))
        try Self.check(data, response)
        return Self.object(data)
    }

    /// Changes some of those fields; the Spark refuses anything outside its list.
    func saveProfileSettings(_ change: [String: Any]) async throws {
        var r = request("api/iphone/settings", method: "PUT")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: change)
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
    }

    /// The voice names to choose from.
    func voices() async throws -> [String] {
        let (data, response) = try await URLSession.shared.data(for: request("api/assistant/voices"))
        try Self.check(data, response)
        return Self.object(data)["voices"] as? [String] ?? []
    }

    /// The Spark's version page (only with the admin's right for this profile).
    func updateState() async throws -> UpdateState {
        var r = request("api/iphone/update")
        r.timeoutInterval = 30
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        let d = Self.object(data)
        let p = d["progress"] as? [String: Any] ?? [:]
        return UpdateState(installed: d["installed"] as? String ?? "", latest: d["latest"] as? String,
                           newer: d["newer"] as? Bool ?? false,
                           changes: (d["changes"] as? [String] ?? []).prefix(30).map { String($0.prefix(160)) },
                           error: d["error"] as? String, running: d["running"] as? Bool ?? false,
                           percent: (p["percent"] as? NSNumber)?.intValue ?? 0, step: p["text"] as? String ?? "",
                           done: p["done"] as? Bool ?? false, ok: p["ok"] as? Bool,
                           start: d["start"] as? Bool ?? false, wait: (d["wait"] as? NSNumber)?.intValue ?? 0)
    }

    /// Starts the update: only with a fresh 6-digit code from the profile's authenticator app.
    func startUpdate(code: String) async throws -> String {
        var r = request("api/iphone/update", method: "POST")
        r.timeoutInterval = 60
        let (data, response) = try await Self.confirmed(r, code: code)
        try Self.check(data, response)
        return Self.object(data)["version"] as? String ?? ""
    }

    /// This iPhone's push address, so the Spark can reach the closed app through Apple.
    /// kind "voip": the PushKit address, calls ring through CallKit with it (Calls.swift).
    func pushToken(_ hex: String, kind: String = "alert") async throws -> Bool {
        try await post("api/iphone/push-token", ["token": hex, "kind": kind])["push"] as? Bool ?? false
    }

    /// The answer as a stream of text and sound, while the Spark is still writing.
    /// car: asked from CarPlay (short answers; the Spark only gets stricter, never looser).
    /// attachment: text from a photo or document; the Spark treats it as outside text (locks actions).
    /// Uploads a photo for the Spark to look at; its id is good for questions in the next 10 minutes.
    func uploadImage(_ data: Data) async throws -> String {
        var r = request("api/chat/image", method: "POST")
        r.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")
        r.httpBody = data
        let (d, response) = try await URLSession.shared.data(for: r)
        if let http = response as? HTTPURLResponse, http.statusCode == 403 || http.statusCode == 415 { throw ImagesOff() }
        try Self.check(d, response)
        guard let id = Self.object(d)["id"] as? String, !id.isEmpty else {
            throw SparkError(message: String(localized: "Der Spark hat das Foto nicht angenommen."))
        }
        return id
    }

    /// What a question takes along: a photo by its id, or, when the Spark does not look at pictures,
    /// the text read on the iPhone as before.
    func chatInput(_ a: Attachment?) async throws -> (Attachment?, [String]) {
        guard let a, let img = a.image else { return (a, []) }
        do {
            let id = try await ImageIds.shared.id(for: img) { try await uploadImage(img) }
            return (nil, [id])
        } catch is ImagesOff {
            guard let ui = UIImage(data: img) else { throw SparkError(message: String(localized: "Die Datei kann ich nicht lesen.")) }
            return (try await Reader.photo(ui, name: a.name, picture: false), [])
        }
    }

    func chat(_ messages: [[String: Any]], car: Bool = false, attachment: Attachment? = nil,
              speak: Bool = true, more: String? = nil) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var retried = false
                    var bytes: URLSession.AsyncBytes
                    while true {
                        // a photo goes up on its own first; the question then names its id
                        let (att, ids) = try await chatInput(attachment)
                        var r = request("api/chat", method: "POST")
                        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
                        r.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                        r.timeoutInterval = 300
                        var body: [String: Any] = ["messages": messages, "tz": TimeZone.current.identifier, "client": "iphone"]
                        if car { body["car"] = true }
                        if !speak { body["speak"] = false }
                        if let m = more { body["more"] = m }
                        if let a = att { body["attachment"] = ["kind": a.kind, "name": a.name, "text": String(a.text.prefix(Reader.chatChars)),
                                                                "cut": a.text.count > Reader.chatChars] }
                        if !ids.isEmpty { body["images"] = ids }
                        r.httpBody = try JSONSerialization.data(withJSONObject: body)
                        let (b, response) = try await URLSession.shared.bytes(for: r)
                        bytes = b
                        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                            // the Spark forgot the photo (expired): upload it again, once
                            if http.statusCode == 410, !retried, let img = attachment?.image {
                                await ImageIds.shared.forget(img)
                                retried = true
                                continue
                            }
                            var data = Data()
                            for try await b in bytes {
                                data.append(b)
                                if data.count > 8192 { break }
                            }
                            try Self.check(data, response)
                        }
                        if let img = attachment?.image { await ImageIds.shared.used(img) }
                        break
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data:") else { continue }
                        let ev = Self.object(Data(line.dropFirst(5).utf8))
                        switch ev["type"] as? String {
                        case "text": cont.yield(.text(ev["delta"] as? String ?? ""))
                        case "retract", "truncated": cont.yield(.drop((ev["drop"] as? NSNumber)?.intValue ?? 0))
                        case "audio":
                            if let s = ev["audio"] as? String, let pcm = Data(base64Encoded: s) { cont.yield(.audio(pcm)) }
                        case "mail": cont.yield(.mark("mail")); cont.yield(.face("mail"))
                        // only these fixed names reach the face, never text from the event
                        case "search", "docsearch", "historysearch": cont.yield(.face("search"))
                        case "calendar", "briefing": cont.yield(.face("calendar"))
                        case "home": cont.yield(.face("home"))
                        case "home_done": cont.yield(.face(ev["ok"] as? Bool == true ? "happy" : "error"))
                        case "memory" where ev["action"] as? String == "saved": cont.yield(.face("memory"))
                        case "outside": cont.yield(.mark("outside"))
                        // a described screen (bedienen.look): sent back as "screen", the Spark keeps only a note
                        case "screen": cont.yield(.mark("screen"))
                        case "error": cont.yield(.error(ev["message"] as? String ?? String(localized: "Fehler beim Spark.")))
                        case "reminder" where ev["foreign"] as? Bool != true:
                            if ev["action"] as? String == "set" { cont.yield(.face("memory")) }
                            if ev["action"] as? String == "set", let item = ev["item"] as? [String: Any], let r = Self.reminder(item) {
                                cont.yield(.reminderSet(r))
                            } else if ev["action"] as? String == "cancel" {
                                cont.yield(.reminderCancel(ev["ids"] as? [String] ?? []))
                            }
                        case "iphone":
                            if let kind = ev["kind"] as? String, let target = ev["target"] as? String { cont.yield(.action(kind: kind, target: target)) }
                        case "bild":
                            // only a job id of 12 hex digits; the prompt is shown as plain text, never as markup
                            if let j = ev["job"] as? String, Self.isJob(j) {
                                cont.yield(.picture(job: j, prompt: String((ev["prompt"] as? String ?? "").prefix(300))))
                            }
                        case "more":
                            // only plain sentences in the app's language and tool names of letters and "_", at most 12
                            let de = Locale.preferredLanguages.first?.hasPrefix("de") ?? true
                            let items = (ev["items"] as? [[String: Any]] ?? []).prefix(12).compactMap { x -> MoreItem? in
                                guard let t = x["text"] as? [String], t.count == 2, let tool = x["tool"] as? String,
                                      (1...40).contains(tool.count), tool.allSatisfy({ $0.isASCII && ($0.isLowercase || $0 == "_") })
                                else { return nil }
                                let s = String((de ? t[0] : t[1]).prefix(200))
                                return s.isEmpty ? nil : MoreItem(text: s, tool: tool)
                            }
                            if !items.isEmpty { cont.yield(.more(kind: String((ev["kind"] as? String ?? "").prefix(10)), items: items)) }
                        case "step":
                            // the readable name in the app's language (plain text, short), ok and the milliseconds
                            let de = Locale.preferredLanguages.first?.hasPrefix("de") ?? true
                            let name = String(((de ? ev["de"] : ev["en"]) as? String ?? "").prefix(60))
                            if !name.isEmpty {
                                let ms = min(max((ev["ms"] as? NSNumber)?.intValue ?? 0, 0), 3_600_000)
                                cont.yield(.step(StepItem(name: name, ok: ev["ok"] as? Bool ?? false, ms: ms)))
                            }
                        case "confirm":
                            // only the kind in fixed words; a tap sends "Ja" or "Nein" like a typed answer
                            let de = Locale.preferredLanguages.first?.hasPrefix("de") ?? true
                            let kind = String(((de ? ev["de"] : ev["en"]) as? String ?? "").prefix(40))
                            if !kind.isEmpty { cont.yield(.confirm(kind)) }
                        case "rate":
                            // only a short id of letters and digits (faelle.py), never other text from the event
                            if let id = ev["id"] as? String, (4...40).contains(id.count),
                               id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber) }) { cont.yield(.rate(id)) }
                        default: break
                        }
                    }
                    cont.finish()
                } catch {
                    cont.finish(throwing: error)
                }
            }
            cont.onTermination = { _ in task.cancel() }
        }
    }
}

// MARK: - Passkey instead of the code

/// Everywhere the Spark wants a fresh code, the app may sign with a passkey instead (V01.0.357): the code is then
/// `SparkAPI.passkey`. The request goes out without a code; the Spark answers "428" with its challenge
/// (X-Speech-Passkey-Options, only over the host name the passkey belongs to), Face ID signs it, and the same
/// request goes out again with the signature (X-Speech-Passkey). Only the app itself signs (Passkey.swift);
/// the extensions have no signer and keep to the code.
/// What the Spark said with "428": whose code, what for, and whether it counts for a while (stufen.py on the Spark).
struct ConfirmInfo {
    var level = ""          // "confirm": counts 10 minutes in this login; "protect": asked every time
    var who = ""
    var what = ""
    var passkey = false     // the person has a passkey for this address
}

extension SparkAPI {
    static let passkey = "passkey"
    /// "Try first" (plan plaene/zweiter-faktor-einheitlich.md, point 4): the request goes out without a code; only when
    /// the Spark answers 428 the app asks (codePrompt), with what the Spark said about it.
    static let probe = "probe"
    /// the app's code window: six digits, SparkAPI.passkey, or nil (cancelled)
    static var codePrompt: ((ConfirmInfo) async -> String?)?

    static func confirmInfo(_ http: HTTPURLResponse) -> ConfirmInfo {
        var i = ConfirmInfo()
        i.passkey = http.value(forHTTPHeaderField: "X-Speech-Passkey-Options") != nil
        if let raw = http.value(forHTTPHeaderField: "X-Speech-Confirm"), raw.count < 4096, let json = unbase64url(raw) {
            let d = object(json)
            let en = Locale.current.language.languageCode?.identifier != "de"
            i.level = d["level"] as? String ?? ""
            i.who = String((d["who"] as? String ?? "").prefix(60))
            i.what = String(((en ? d["what_en"] : d["what"]) as? String ?? d["what"] as? String ?? "").prefix(120))
        }
        return i
    }
    /// the app's signer: (challenge from the Spark {"sid", "options"}, host name) -> the answer {"sid", "response"}
    static var passkeySigner: (([String: Any], String) async throws -> [String: Any])?

    static func base64url(_ d: Data) -> String {
        d.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func unbase64url(_ s: String) -> Data? {
        var b = s.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        b += String(repeating: "=", count: (4 - b.count % 4) % 4)
        return Data(base64Encoded: b)
    }

    /// A passkey can work here: the app can sign and the Spark is reached by a host name, not an IP address.
    static var passkeyPossible: Bool {
        guard passkeySigner != nil, let host = Store.baseURL?.host, host.contains(".") else { return false }
        return host.range(of: #"^[0-9.]+$"#, options: .regularExpression) == nil && !host.contains(":")
    }

    /// Sends a request that may need a code: six digits, `SparkAPI.passkey`, or nil.
    static func confirmed(_ request: URLRequest, code: String?, session: URLSession = .shared) async throws -> (Data, URLResponse) {
        if code == probe {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 428, let ask = codePrompt else { return (data, response) }
            guard let answer = await ask(confirmInfo(http)) else {
                throw SparkError(message: String(localized: "Abgebrochen: ohne Code keine Änderung."))
            }
            return try await confirmed(request, code: answer, session: session)
        }
        var r = request
        if let code, code != passkey { r.setValue(code, forHTTPHeaderField: "X-Speech-Code") }
        let (data, response) = try await session.data(for: r)
        guard code == passkey, let http = response as? HTTPURLResponse, http.statusCode == 428 else { return (data, response) }
        guard let raw = http.value(forHTTPHeaderField: "X-Speech-Passkey-Options"), raw.count < 8192,
              let json = unbase64url(raw), let options = object(json) as [String: Any]?, !options.isEmpty,
              let sign = passkeySigner, let host = r.url?.host else {
            throw SparkError(message: String(localized: "Hier gibt es keinen Passkey. Lege ihn in Safari über die Adresse mit Namen unter Ich → Sicherheit an, oder nimm den Code."))
        }
        let answer = try JSONSerialization.data(withJSONObject: try await sign(options, host))
        r.setValue(base64url(answer), forHTTPHeaderField: "X-Speech-Passkey")
        return try await session.data(for: r)
    }
}
