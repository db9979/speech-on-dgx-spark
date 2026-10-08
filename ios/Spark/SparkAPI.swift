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
        guard let http = response as? HTTPURLResponse else { throw SparkError(message: "Keine Antwort vom Spark.") }
        guard !(200..<300).contains(http.statusCode) else { return }
        let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
        switch http.statusCode {
        case 401:
            throw SparkError(message: "Der Spark nimmt dieses iPhone nicht an. Im Panel unter Ich → iPhone-App prüfen, ob die App an ist, sonst neu koppeln.")
        case 429:
            throw SparkError(message: "Der Spark ist gerade ausgelastet. Bitte gleich noch einmal.")
        case 503:
            throw SparkError(message: "Die Spracherkennung oder das Sprachmodell läuft gerade nicht.")
        default:
            throw SparkError(message: detail ?? "Fehler \(http.statusCode) vom Spark.")
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
            throw SparkError(message: "Der Spark hat keinen Schlüssel geschickt.")
        }
        return (key, d["profile"] as? String ?? "", d["language"] as? String ?? "auto")
    }

    /// Checks the key: whose it is and what the profile allows the app.
    func hello() async throws -> Allowed {
        let (data, response) = try await URLSession.shared.data(for: request("api/iphone/hello"))
        try Self.check(data, response)
        let d = Self.object(data)
        return Allowed(profile: d["profile"] as? String ?? "", language: d["language"] as? String ?? "auto",
                       listen: d["listen"] as? Bool ?? false, act: d["act"] as? Bool ?? false,
                       proactive: d["proactive"] as? Bool ?? false, reminders: d["reminders"] as? Bool ?? true,
                       face: d["face"] as? String == "comic" ? "comic" : "robot")
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

    /// The answer as a stream of text and sound, while the Spark is still writing.
    func chat(_ messages: [[String: Any]]) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var r = request("api/chat", method: "POST")
                    r.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    r.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    r.timeoutInterval = 300
                    r.httpBody = try JSONSerialization.data(withJSONObject: [
                        "messages": messages, "tz": TimeZone.current.identifier, "client": "iphone"])
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
                        case "error": cont.yield(.error(ev["message"] as? String ?? "Fehler beim Spark."))
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
