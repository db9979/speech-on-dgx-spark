import Foundation

/// What can go wrong with a call to the Spark (contract, "Errors"). The texts are German and shown as plain text.
enum SparkProblem: Error {
    case unknownDevice          // 401: the key was removed in the panel
    case off(String)            // 403: this part is switched off
    case busy(String)           // 429
    case notaus(String)         // 503 with "Notaus …" / "Mein Notaus …"
    case failed(String)         // any other answer of the Spark (400, 413, 500, …)
    case offline(String)        // no answer at all

    var message: String {
        switch self {
        case .unknownDevice: return "Der Spark kennt dieses Gerät nicht mehr. Neu koppeln."
        case .off(let m), .busy(let m), .notaus(let m), .failed(let m), .offline(let m): return m
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
    func improve(text: String, art: String, sprache: String?, wunsch: String) async throws -> WriteOutcome {
        var body: [String: Any] = ["text": text, "art": art]
        if let sprache, !sprache.isEmpty { body["sprache"] = sprache }
        let w = wunsch.trimmingCharacters(in: .whitespacesAndNewlines)
        if !w.isEmpty { body["wunsch"] = String(w.prefix(300)) }
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

    /// POST /api/desk/ask (the Spark keeps follow-ups in context itself).
    func ask(_ text: String) async throws -> String {
        let d = try await postJSON("api/desk/ask", ["text": text, "tz": TimeZone.current.identifier], timeout: 190)
        guard let a = d["answer"] as? String else { throw SparkProblem.failed("Keine Antwort vom Spark.") }
        return a
    }

    /// POST /api/desk/dictate with the recording as WAV.
    func dictate(wav: Data, sprache: String) async throws -> String {
        var form = Multipart()
        form.field("sprache", sprache)
        form.file("file", filename: "diktat.wav", type: "audio/wav", data: wav)
        let d = try await postMultipart("api/desk/dictate", form, timeout: 120)
        return (d["text"] as? String) ?? ""
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
