import Foundation

struct SparkError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// What the answer stream of /api/chat brings (Server-Sent Events, see app/panel/chat.py).
enum ChatEvent {
    case text(String)
    case drop(Int)          // the last characters were taken back
    case audio(Data)        // 16-bit PCM, 24 kHz, mono
    case mark(String)       // "mail" or "outside": the answer rests on text from outside
    case error(String)
    case reminderSet(Reminder)
    case reminderCancel([String])
    case action(kind: String, target: String)   // iphone_action: "navigate" or "call"
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
}

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
struct Allowed {
    var profile = ""
    var language = "auto"
    var listen = false
    var act = false
    var proactive = false
    var reminders = true
    var face = "robot"
    var push = false
    var carHa = false
    var docs = false
    var ios = false
    /// Spark updates (rights only from the admin): notices and the version page, starting the update
    var updateNotify = false
    var updateStart = false
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

/// The Spark's panel, spoken to with this iPhone's own device key. The key may only ask and
/// listen (chat, speech recognition, the Siri question, hello); the panel refuses everything else.
struct SparkAPI {
    let base: URL
    let key: String?

    static var current: SparkAPI? {
        guard let base = Store.baseURL, let key = Store.key else { return nil }
        return SparkAPI(base: base, key: key)
    }

    private func request(_ path: String, method: String = "GET") -> URLRequest {
        var r = URLRequest(url: base.appendingPathComponent(path))
        r.httpMethod = method
        r.timeoutInterval = 120
        if let key { r.setValue(key, forHTTPHeaderField: "X-Speech-Device") }
        return r
    }

    private static func check(_ data: Data, _ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { throw SparkError(message: String(localized: "Keine Antwort vom Spark.")) }
        guard !(200..<300).contains(http.statusCode) else { return }
        let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
        switch http.statusCode {
        case 401:
            throw SparkError(message: String(localized: "Der Spark nimmt dieses iPhone nicht an. Im Panel unter Ich → iPhone-App prüfen, ob die App an ist, sonst neu koppeln."))
        case 428:
            throw SparkError(message: String(localized: "Der Code stimmt nicht. Bitte den aktuellen Code aus der Authenticator-App nehmen."))
        case 429 where (detail ?? "").hasPrefix("Das Update"):   // one start from the app per 10 minutes
            throw SparkError(message: detail ?? "")
        case 429:
            throw SparkError(message: String(localized: "Der Spark ist gerade ausgelastet. Bitte gleich noch einmal."))
        case 503:
            throw SparkError(message: String(localized: "Die Spracherkennung oder das Sprachmodell läuft gerade nicht."))
        default:
            throw SparkError(message: detail ?? String(localized: "Fehler \(http.statusCode) vom Spark."))
        }
    }

    private static func object(_ data: Data) -> [String: Any] {
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
                       face: d["face"] as? String == "comic" ? "comic" : "robot",
                       push: d["push"] as? Bool ?? false, carHa: d["car_ha"] as? Bool ?? false,
                       docs: d["docs"] as? Bool ?? false, ios: d["ios"] as? Bool ?? false,
                       updateNotify: (d["update"] as? [String: Any])?["notify"] as? Bool ?? false,
                       updateStart: (d["update"] as? [String: Any])?["start"] as? Bool ?? false)
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
    func transcribe(wav: Data, language: String) async throws -> String {
        let boundary = "spark-" + UUID().uuidString
        var r = request("api/test/asr", method: "POST")
        r.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n\(language)\r\n".utf8))
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

    /// Adds or replaces one conversation in the profile's list.
    func saveConvo(id: String, title: String, msgs: [[String: Any]]) async throws {
        var r = request("api/profile/convos", method: "PUT")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: [
            "id": id, "title": String(title.prefix(80)), "msgs": msgs,
            "updated": Int(Date().timeIntervalSince1970 * 1000)])
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
    }

    /// A document's text into the profile's "Meine Dokumente" (only with the profile's switch).
    func storeDoc(name: String, text: String) async throws {
        var r = request("api/iphone/doc", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.timeoutInterval = 120
        r.httpBody = try JSONSerialization.data(withJSONObject: ["name": String(name.prefix(100)), "text": text])
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
    }

    /// New entries of a Spark list ("einkauf", "aufgaben"); the Spark hands each one over once.
    func takeList(_ list: String) async throws -> [String] {
        var c = URLComponents(url: base.appendingPathComponent("api/tasks/inbox"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "list", value: list), URLQueryItem(name: "format", value: "json")]
        var r = request("api/tasks/inbox", method: "POST")
        r.url = c.url
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return (Self.object(data)["items"] as? [String] ?? []).filter { !$0.isEmpty }
    }

    /// Puts entries on a Spark list (from Shortcuts; comma or line separated).
    func addToList(_ list: String, _ text: String) async throws {
        _ = try await post("api/profile/tasks/" + list, ["text": String(text.prefix(2000))])
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
        r.setValue(code, forHTTPHeaderField: "X-Speech-Code")
        r.timeoutInterval = 60
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return Self.object(data)["version"] as? String ?? ""
    }

    /// This iPhone's push address, so the Spark can reach the closed app through Apple.
    func pushToken(_ hex: String) async throws -> Bool {
        try await post("api/iphone/push-token", ["token": hex])["push"] as? Bool ?? false
    }

    /// The answer as a stream of text and sound, while the Spark is still writing.
    /// car: asked from CarPlay (short answers; the Spark only gets stricter, never looser).
    /// attachment: text from a photo or document; the Spark treats it as outside text (locks actions).
    func chat(_ messages: [[String: Any]], car: Bool = false, attachment: Attachment? = nil,
              speak: Bool = true) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var r = request("api/chat", method: "POST")
                    r.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    r.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    r.timeoutInterval = 300
                    var body: [String: Any] = ["messages": messages, "tz": TimeZone.current.identifier, "client": "iphone"]
                    if car { body["car"] = true }
                    if !speak { body["speak"] = false }
                    if let a = attachment { body["attachment"] = ["kind": a.kind, "name": a.name, "text": String(a.text.prefix(Reader.chatChars))] }
                    r.httpBody = try JSONSerialization.data(withJSONObject: body)
                    let (bytes, response) = try await URLSession.shared.bytes(for: r)
                    if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                        var data = Data()
                        for try await b in bytes {
                            data.append(b)
                            if data.count > 8192 { break }
                        }
                        try Self.check(data, response)
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data:") else { continue }
                        let ev = Self.object(Data(line.dropFirst(5).utf8))
                        switch ev["type"] as? String {
                        case "text": cont.yield(.text(ev["delta"] as? String ?? ""))
                        case "retract", "truncated": cont.yield(.drop((ev["drop"] as? NSNumber)?.intValue ?? 0))
                        case "audio":
                            if let s = ev["audio"] as? String, let pcm = Data(base64Encoded: s) { cont.yield(.audio(pcm)) }
                        case "mail": cont.yield(.mark("mail"))
                        case "outside": cont.yield(.mark("outside"))
                        case "error": cont.yield(.error(ev["message"] as? String ?? String(localized: "Fehler beim Spark.")))
                        case "reminder" where ev["foreign"] as? Bool != true:
                            if ev["action"] as? String == "set", let item = ev["item"] as? [String: Any], let r = Self.reminder(item) {
                                cont.yield(.reminderSet(r))
                            } else if ev["action"] as? String == "cancel" {
                                cont.yield(.reminderCancel(ev["ids"] as? [String] ?? []))
                            }
                        case "iphone":
                            if let kind = ev["kind"] as? String, let target = ev["target"] as? String { cont.yield(.action(kind: kind, target: target)) }
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
