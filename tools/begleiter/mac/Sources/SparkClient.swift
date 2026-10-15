import Foundation

/// What can go wrong with a call to the Spark (contract, "Errors"). The texts are German and shown as plain text.
enum SparkProblem: Error {
    case unknownDevice          // 401: the key was removed in the panel
    case off(String)            // 403: this part is switched off
    case busy(String)           // 429
    case notaus(String)         // 503 with "Notaus …" / "Mein Notaus …"
    case conflict(String)       // 409 (e.g. the same file is already in the Wissen)
    case failed(String)         // any other answer of the Spark (400, 413, 500, …)
    case offline(String)        // no answer at all

    var message: String {
        switch self {
        case .unknownDevice: return "Der Spark kennt dieses Gerät nicht mehr. Neu koppeln."
        case .off(let m), .busy(let m), .notaus(let m), .conflict(let m), .failed(let m), .offline(let m): return m
        }
    }
}

/// The talk with one Spark: only its base address, an ephemeral session (no cookies, no cache, no stored
/// credentials), no redirects, the device key only in the header "X-Speech-Device". Nothing is logged.
final class SparkClient: NSObject, URLSessionTaskDelegate, @unchecked Sendable {   // session is set once in init
    let base: String
    private let key: String?
    private var session: URLSession!
    /// for the update file only: same rules, more time
    private var fileSession: URLSession!

    init(base: String, key: String?) {
        self.base = base
        self.key = key
        super.init()
        let c = URLSessionConfiguration.ephemeral
        c.httpCookieAcceptPolicy = .never
        c.httpShouldSetCookies = false
        c.httpCookieStorage = nil
        c.urlCache = nil
        c.urlCredentialStorage = nil
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.timeoutIntervalForRequest = 200
        c.timeoutIntervalForResource = 240
        session = URLSession(configuration: c, delegate: self, delegateQueue: nil)
        let f = URLSessionConfiguration.ephemeral
        f.httpCookieAcceptPolicy = .never
        f.httpShouldSetCookies = false
        f.httpCookieStorage = nil
        f.urlCache = nil
        f.urlCredentialStorage = nil
        f.requestCachePolicy = .reloadIgnoringLocalCacheData
        f.timeoutIntervalForRequest = 60
        f.timeoutIntervalForResource = 1800
        fileSession = URLSession(configuration: f, delegate: self, delegateQueue: nil)
    }

    /// Stops everything still running; the client is not used again afterwards.
    func close() {
        session.invalidateAndCancel()
        fileSession.invalidateAndCancel()
    }

    // The Spark answers itself: a redirect (perhaps to another host) is never followed.
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }

    // ------------------------------------------------------------------ calls

    func get(_ path: String, timeout: TimeInterval = 20) async throws -> [String: Any] {
        let r = try request(path, method: "GET", timeout: timeout)
        return try await send(r)
    }

    func postJSON(_ path: String, _ body: [String: Any], timeout: TimeInterval) async throws -> [String: Any] {
        var r = try request(path, method: "POST", timeout: timeout)
        r.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(r)
    }

    func postMultipart(_ path: String, _ form: Multipart, timeout: TimeInterval) async throws -> [String: Any] {
        var r = try request(path, method: "POST", timeout: timeout)
        r.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        r.httpBody = form.finished()
        return try await send(r)
    }

    private func request(_ path: String, method: String, timeout: TimeInterval) throws -> URLRequest {
        guard let url = URL(string: base + "/" + path) else {
            throw SparkProblem.failed("Die Adresse des Spark ist ungültig.")
        }
        var r = URLRequest(url: url)
        r.httpMethod = method
        r.timeoutInterval = timeout
        r.httpShouldHandleCookies = false
        r.cachePolicy = .reloadIgnoringLocalCacheData
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        if let key {
            r.setValue(key, forHTTPHeaderField: "X-Speech-Device")
        }
        return r
    }

    private func send(_ r: URLRequest) async throws -> [String: Any] {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: r)
        } catch {
            throw Self.transportProblem(error)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let obj = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any]) ?? [:]
        if (200..<300).contains(status) {
            return obj
        }
        throw Self.problem(status: status, obj)
    }

    /// POST with a JSON body whose answer is bytes (the voice for "Vorlesen"); error answers as everywhere.
    func postJSONForData(_ path: String, _ body: [String: Any], timeout: TimeInterval, maxBytes: Int) async throws -> Data {
        var r = try request(path, method: "POST", timeout: timeout)
        r.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        r.setValue("audio/wav, application/octet-stream, application/json", forHTTPHeaderField: "Accept")
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: r)
        } catch {
            throw Self.transportProblem(error)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let obj = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any]) ?? [:]
            throw Self.problem(status: status, obj)
        }
        guard !data.isEmpty, data.count <= maxBytes else {
            throw SparkProblem.failed("Der Spark hat keine brauchbare Antwort geschickt.")
        }
        return data
    }

    /// GET of a file (the update): the bytes go to `destination` (replaced if there); nothing else is kept.
    /// At most `maxBytes`; an error answer of the Spark becomes a SparkProblem as everywhere.
    func download(_ path: String, to destination: URL, maxBytes: Int) async throws {
        var r = try request(path, method: "GET", timeout: 60)
        r.setValue("application/octet-stream", forHTTPHeaderField: "Accept")
        let tmp: URL
        let response: URLResponse
        do {
            (tmp, response) = try await fileSession.download(for: r)
        } catch {
            throw Self.transportProblem(error)
        }
        let fm = FileManager.default
        defer { try? fm.removeItem(at: tmp) }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let small = ((try? fm.attributesOfItem(atPath: tmp.path)[.size]) as? NSNumber)?.intValue ?? 0
            var obj: [String: Any] = [:]
            if small > 0 && small < 64 * 1024, let data = try? Data(contentsOf: tmp) {
                obj = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any]) ?? [:]
            }
            if status == 404 {
                throw SparkProblem.failed(Self.detail(obj) ?? "Der Spark hat gerade keine neue Version für den Mac.")
            }
            throw Self.problem(status: status, obj)
        }
        let size = ((try? fm.attributesOfItem(atPath: tmp.path)[.size]) as? NSNumber)?.intValue ?? 0
        guard size > 0, size <= maxBytes else {
            throw SparkProblem.failed("Update beschädigt, nichts geändert.")
        }
        try? fm.removeItem(at: destination)
        do {
            try fm.moveItem(at: tmp, to: destination)
        } catch {
            throw SparkProblem.failed("Das Update ließ sich nicht speichern.")
        }
    }

    private static func transportProblem(_ error: Error) -> Error {
        if let e = error as? URLError {
            if e.code == .cancelled { return CancellationError() }
            if e.code == .timedOut { return SparkProblem.offline("Der Spark hat nicht rechtzeitig geantwortet.") }
            if e.code == .appTransportSecurityRequiresSecureConnection {
                return SparkProblem.offline("Unverschlüsselt (http) nur im Heimnetz.")
            }
            return SparkProblem.offline("Der Spark ist nicht erreichbar.")
        }
        if error is CancellationError { return CancellationError() }
        return SparkProblem.offline("Der Spark ist nicht erreichbar.")
    }

    /// What a non-2xx answer means (contract, "Errors").
    private static func problem(status: Int, _ obj: [String: Any]) -> SparkProblem {
        let detail = Self.detail(obj)
        switch status {
        case 401:
            return .unknownDevice
        case 403:
            return .off(detail ?? "Dieser Teil ist im Panel aus (Ich → Begleiter).")
        case 409:
            return .conflict(detail ?? "Das ist schon da.")
        case 429:
            return .busy(detail ?? "Der Spark arbeitet noch. Bitte gleich noch einmal.")
        case 503:
            if let d = detail, d.hasPrefix("Notaus") || d.hasPrefix("Mein Notaus") {
                return .notaus(d)
            }
            return .offline(detail ?? "Der Spark ist gerade nicht bereit.")
        default:
            if (300..<400).contains(status) {
                return .failed("Der Spark hat auf eine andere Adresse verwiesen. Bitte neu koppeln.")
            }
            return .failed(detail ?? "Der Spark hat mit Fehler \(status) geantwortet.")
        }
    }

    /// The Spark's own words ({"detail": "…"}), cleaned for plain display; nil if there are none.
    static func detail(_ obj: [String: Any]) -> String? {
        guard let raw = obj["detail"] as? String else { return nil }
        let clean = String(raw.unicodeScalars.map { s -> Character in
            (s.properties.generalCategory == .control && s != "\n") ? " " : Character(s)
        })
        let t = clean.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        return t.count > 500 ? String(t.prefix(500)) + " …" : t
    }
}

// ------------------------------------------------------------------ the parts' calls

struct WriteOutcome {
    let text: String
    /// ("=", same), ("-", removed), ("+", added); nil when the Spark sends none (translations)
    let diff: [(op: String, text: String)]?
    let changes: Int?
    let ms: Int?
}

extension SparkClient {
    static let writeMax = 20000
    static let askMax = 2000

    /// POST /api/write/assist; "sprache" only for translations, "wunsch" only when given.
    /// `app`: the front app's category (only when part "context" is on), `mail`: the mail to answer (art "antwort").
    func improve(text: String, art: String, sprache: String?, wunsch: String, app: String? = nil,
                 mail: String? = nil) async throws -> WriteOutcome {
        var body: [String: Any] = ["text": text, "art": art]
        if let sprache, !sprache.isEmpty { body["sprache"] = sprache }
        let w = wunsch.trimmingCharacters(in: .whitespacesAndNewlines)
        if !w.isEmpty { body["wunsch"] = String(w.prefix(300)) }
        if let app, AppCategory.all.contains(app) { body["app"] = app }
        if let mail { body["mail"] = String(mail.prefix(SparkClient.writeMax)) }
        let d = try await postJSON("api/write/assist", body, timeout: 190)
        guard let out = d["text"] as? String else {
            throw SparkProblem.failed("Keine Antwort vom Spark.")
        }
        let diff: [(op: String, text: String)]? = (d["diff"] as? [Any])?.compactMap { item -> (op: String, text: String)? in
            guard let p = item as? [Any], p.count == 2, let op = p[0] as? String, ["=", "-", "+"].contains(op),
                  let s = p[1] as? String else { return nil }
            return (op: op, text: s)
        }
        return WriteOutcome(text: out, diff: diff, changes: (d["changes"] as? NSNumber)?.intValue,
                            ms: (d["ms"] as? NSNumber)?.intValue)
    }

    /// POST /api/desk/ask (the Spark keeps follow-ups in context itself): the plain answer.
    func ask(_ text: String, note: Int? = nil) async throws -> String {
        try await askRich(text, note: note).answer
    }

    /// The same with "md", the answer with Markdown for showing it formatted (missing from older Sparks);
    /// "answer" stays the plain text for reading aloud and copying.
    func askRich(_ text: String, note: Int? = nil) async throws -> (answer: String, md: String?) {
        var body: [String: Any] = ["text": String(text.prefix(SparkClient.askMax)), "tz": TimeZone.current.identifier]
        if let note { body["note"] = note }
        let d = try await postJSON("api/desk/ask", body, timeout: 190)
        guard let a = d["answer"] as? String else { throw SparkProblem.failed("Keine Antwort vom Spark.") }
        return (a, d["md"] as? String)
    }

    /// POST /api/desk/dictate with the recording as WAV.
    func dictate(wav: Data, sprache: String) async throws -> String {
        var form = Multipart()
        form.field("sprache", sprache)
        form.file("file", filename: "diktat.wav", type: "audio/wav", data: wav)
        let d = try await postMultipart("api/desk/dictate", form, timeout: 120)
        return (d["text"] as? String) ?? ""
    }

    /// POST /api/desk/file: "text" for zusammenfassen/uebersetzen/erklaeren; for wissen the stored name.
    func file(_ data: Data, name: String, type: String, what: String, sprache: String?) async throws -> String {
        var form = Multipart()
        form.field("what", what)
        if let sprache, what == "uebersetzen" { form.field("sprache", sprache) }
        form.file("file", filename: FileKinds.safeName(name), type: type, data: data)
        let d = try await postMultipart("api/desk/file", form, timeout: 300)
        if what == "wissen" { return (d["name"] as? String) ?? name }
        guard let t = d["text"] as? String else { throw SparkProblem.failed("Keine Antwort vom Spark.") }
        return t
    }

    /// POST /api/desk/screen with the picture (PNG or JPEG).
    func screen(_ image: Data, type: String, question: String, what: String) async throws -> String {
        var form = Multipart()
        form.field("what", what)
        form.field("question", String(question.prefix(ScreenShot.maxQuestion)))
        form.file("image", filename: type == "image/png" ? "bildschirm.png" : "bildschirm.jpg", type: type, data: image)
        let d = try await postMultipart("api/desk/screen", form, timeout: 240)
        guard let t = d["text"] as? String else { throw SparkProblem.failed("Keine Antwort vom Spark.") }
        return t
    }

    /// POST /api/desk/hear: was the wake word in it, and what came after it.
    func hear(wav: Data) async throws -> (wake: Bool, rest: String) {
        var form = Multipart()
        form.file("file", filename: "hoeren.wav", type: "audio/wav", data: wav)
        let d = try await postMultipart("api/desk/hear", form, timeout: 30)
        return ((d["wake"] as? Bool) ?? false, ((d["rest"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// POST /api/desk/act: the answer to one of the Spark's wishes.
    func act(id: String, ok: Bool, error: String?) async throws {
        var body: [String: Any] = ["id": id, "ok": ok]
        if let error, !error.isEmpty { body["error"] = String(error.prefix(300)) }
        _ = try await postJSON("api/desk/act", body, timeout: 30)
    }

    /// POST /api/desk/pair (without key): the new key and the profile's name.
    func pair(code: String, name: String) async throws -> (key: String, profile: String) {
        let d = try await postJSON("api/desk/pair", ["code": code, "name": name, "kind": "mac"], timeout: 30)
        guard let key = d["key"] as? String, key.hasPrefix("sd_"), key.count < 200,
              key.unicodeScalars.allSatisfy({ $0.isASCII && $0.value > 32 && $0.value < 127 }) else {
            throw SparkProblem.failed("Der Spark hat keinen gültigen Schlüssel geschickt.")
        }
        return (key, (d["profile"] as? String) ?? "")
    }
}

// ------------------------------------------------------------------ Version 4 calls

extension SparkClient {
    /// POST /api/desk/speak: the text in the profile's own voice (WAV, whole file).
    func speak(_ text: String) async throws -> Data {
        try await postJSONForData("api/desk/speak", ["text": String(text.prefix(SpeakText.max))], timeout: 180,
                                  maxBytes: 80 * 1024 * 1024)
    }

    /// GET /api/desk/inbox/file?id=… into `destination` (≤ 20 MB).
    func inboxFile(id: String, to destination: URL) async throws {
        guard ActAsk.validID(id) else { throw SparkProblem.failed("Ungültige Kennung.") }
        try await download("api/desk/inbox/file?id=\(id)", to: destination, maxBytes: InboxItem.maxFile)
    }

    /// POST /api/desk/inbox/done
    func inboxDone(id: String) async throws {
        _ = try await postJSON("api/desk/inbox/done", ["id": id], timeout: 30)
    }

    /// GET /api/desk/agenda
    func agenda() async throws -> Agenda {
        Agenda(try await get("api/desk/agenda", timeout: 30))
    }

    /// POST /api/desk/remind for a note (or a text): when it will come.
    func remind(note: Int? = nil, text: String? = nil, minutes: Int) async throws -> Date? {
        var body: [String: Any] = ["minutes": Remind.minutes(minutes)]
        if let note { body["note"] = note }
        if let text { body["text"] = String(text.prefix(300)) }
        let d = try await postJSON("api/desk/remind", body, timeout: 30)
        return IsoDate.parse(d["due"])
    }

    /// POST /api/desk/busy
    func busy(_ on: Bool, why: String?) async throws {
        var body: [String: Any] = ["busy": on]
        if on, let why { body["why"] = why }
        _ = try await postJSON("api/desk/busy", body, timeout: 20)
    }

    /// POST /api/desk/meeting/start -> id
    func meetingStart() async throws -> String {
        let d = try await postJSON("api/desk/meeting/start", [:], timeout: 30)
        let id: String
        if let s = d["id"] as? String { id = s } else if let n = d["id"] as? NSNumber { id = n.stringValue } else { id = "" }
        guard !id.isEmpty, id.count <= 200 else { throw SparkProblem.failed("Der Spark hat keine Besprechung angelegt.") }
        return id
    }

    /// POST /api/desk/meeting/chunk (WAV 16 kHz mono ≤ 60 s) -> chars so far
    func meetingChunk(id: String, wav: Data) async throws -> Int {
        var form = Multipart()
        form.field("id", id)
        form.file("file", filename: "besprechung.wav", type: "audio/wav", data: wav)
        let d = try await postMultipart("api/desk/meeting/chunk", form, timeout: 120)
        return (d["chars"] as? NSNumber)?.intValue ?? 0
    }

    /// POST /api/desk/meeting/end -> summary and tasks
    func meetingEnd(id: String) async throws -> MeetingResult {
        MeetingResult(try await postJSON("api/desk/meeting/end", ["id": id], timeout: 300))
    }

    /// POST /api/desk/meeting/keep -> (reminders, remarkable)
    func meetingKeep(id: String, tasks: [Int], remarkable: Bool) async throws -> (reminders: Int, remarkable: Bool) {
        let d = try await postJSON("api/desk/meeting/keep", ["id": id, "tasks": tasks, "remarkable": remarkable],
                                   timeout: 120)
        return ((d["reminders"] as? NSNumber)?.intValue ?? 0, (d["remarkable"] as? Bool) ?? false)
    }

    /// GET /api/desk/home
    func homeButtons() async throws -> [HomeButton] {
        HomeButton.list(try await get("api/desk/home", timeout: 30)["buttons"])
    }

    /// POST /api/desk/home (the code word only in the body, only when asked for)
    func homePress(id: String, code: String?) async throws -> String? {
        var body: [String: Any] = ["id": id]
        if let code, !code.isEmpty { body["code"] = code }
        let d = try await postJSON("api/desk/home", body, timeout: 30)
        return HomeButton.state(d["state"])
    }

    /// GET /api/desk/daily?kind=morning|evening: the text without signs (notification) and "md", the morning
    /// with Markdown for the window of "Frag Spark" (missing from older Sparks and for the evening)
    func daily(_ kind: String) async throws -> (text: String, md: String?) {
        let k = kind == "evening" ? "evening" : "morning"
        let d = try await get("api/desk/daily?kind=\(k)", timeout: 120)
        guard let t = d["text"] as? String else { throw SparkProblem.failed("Keine Antwort vom Spark.") }
        return (t, d["md"] as? String)
    }
}
