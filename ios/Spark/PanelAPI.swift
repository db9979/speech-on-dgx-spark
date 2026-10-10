import Foundation

/// Panel areas in the app (plan plaene/iphone-uebernimmt-panel.md): the same /api paths as the panel,
/// with this iPhone's key. The Spark opens each area only with the admin switch and the profile's own
/// switch for it; all rules stay on the Spark.
extension SparkAPI {
    /// One JSON request; code: a fresh 6-digit code from the authenticator app when the Spark wants one.
    func call(_ method: String, _ path: String, query: [String: String] = [:], body: [String: Any]? = nil,
              code: String? = nil, timeout: TimeInterval = 60) async throws -> Any {
        var r = request(path, method: method)
        if !query.isEmpty {
            var c = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
            c.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
            r.url = c.url
        }
        r.timeoutInterval = timeout
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        if let code { r.setValue(code, forHTTPHeaderField: "X-Speech-Code") }
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return (try? JSONSerialization.jsonObject(with: data)) ?? [:]
    }

    func object(_ method: String, _ path: String, query: [String: String] = [:], body: [String: Any]? = nil,
                code: String? = nil, timeout: TimeInterval = 60) async throws -> [String: Any] {
        try await call(method, path, query: query, body: body, code: code, timeout: timeout) as? [String: Any] ?? [:]
    }

    /// A page of the panel in Safari ("Im Panel öffnen"): #go=<page>, #cfg=<settings page> or #me=<Ich area>.
    static func panelLink(_ place: String) -> URL? {
        guard let base = Store.baseURL, place.range(of: #"^(go|cfg|me)=[a-z]{2,12}$"#, options: .regularExpression) != nil
        else { return nil }
        return URL(string: base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/#" + place)
    }
}

/// A fact the assistant keeps about the profile (Ich → Gedächtnis).
struct Fact: Identifiable, Hashable {
    let id: String
    let text: String
    let learned: Bool
}

/// The assistant's proposal to tidy up the memory: facts to merge and facts to drop.
struct MemoryTidy {
    var merge: [(old: [String], text: String)] = []
    var drop: [(old: String, why: String)] = []
}

extension SparkAPI {
    static func id(_ s: String) -> Bool { s.range(of: #"^[0-9a-f]{1,16}$"#, options: .regularExpression) != nil }

    func memory() async throws -> (facts: [Fact], tidy: MemoryTidy?) {
        let d = try await object("GET", "api/profile/memory")
        let facts = (d["facts"] as? [[String: Any]] ?? []).compactMap { f -> Fact? in
            guard let id = f["id"] as? String, Self.id(id) else { return nil }
            return Fact(id: id, text: f["text"] as? String ?? "", learned: f["auto"] as? Bool ?? false)
        }
        return (facts.reversed(), Self.tidy(d["tidy"]))
    }

    static func tidy(_ any: Any?) -> MemoryTidy? {
        guard let t = any as? [String: Any] else { return nil }
        var m = MemoryTidy()
        m.merge = (t["merge"] as? [[String: Any]] ?? []).map { ($0["old"] as? [String] ?? [], $0["text"] as? String ?? "") }
        m.drop = (t["drop"] as? [[String: Any]] ?? []).map { ($0["old"] as? String ?? "", $0["why"] as? String ?? "") }
        return m.merge.isEmpty && m.drop.isEmpty ? nil : m
    }

    func forget(_ id: String) async throws {
        guard Self.id(id) else { return }
        _ = try await call("DELETE", "api/profile/memory/\(id)")
    }

    /// "check" asks the language model for a proposal, "accept" carries it out, "reject" drops it.
    func tidyMemory(_ step: String) async throws -> MemoryTidy? {
        let d = try await object("POST", "api/profile/memory/tidy", body: ["do": step], timeout: 180)
        return Self.tidy(d["tidy"])
    }

    /// The next appointments of the connected calendars (the same lines as in the panel).
    func nextEvents() async throws -> (events: [String], errors: [String]) {
        let d = try await object("POST", "api/profile/calendar/test", body: ["tz": TimeZone.current.identifier])
        return (d["events"] as? [String] ?? [], d["errors"] as? [String] ?? [])
    }

    func deleteReminder(_ id: String) async throws {
        guard Self.id(id) else { return }
        _ = try await call("DELETE", "api/profile/reminders/\(id)")
    }
}

// MARK: - Dokumente verwalten, Stimme, Von selbst, Sicherheit, Konten (each its own area switch)

extension SparkAPI {
    static func isDoc(_ s: String) -> Bool { s.range(of: #"^[0-9a-f]{12}$"#, options: .regularExpression) != nil }
    static func devId(_ s: String) -> Bool { s.range(of: #"^d_[0-9a-f]{12}$"#, options: .regularExpression) != nil }
    static func accId(_ s: String) -> Bool { s.range(of: #"^[mck][0-9a-f]{8}$"#, options: .regularExpression) != nil }

    /// One of the profile's own documents: "Für alle", searchable or not, own tags (nil: the automatic ones).
    func setDoc(_ id: String, _ body: [String: Any]) async throws {
        guard Self.isDoc(id) else { return }
        _ = try await call("PUT", "api/profile/wissen/\(id)", body: body)
    }

    func deleteDoc(_ id: String) async throws {
        guard Self.isDoc(id) else { return }
        _ = try await call("DELETE", "api/profile/docs/\(id)")
    }

    /// "reread" or "remind" (a reminder before the document's deadline)
    func docAction(_ id: String, _ action: String) async throws -> [String: Any] {
        guard Self.isDoc(id), ["reread", "remind"].contains(action) else { return [:] }
        return try await object("POST", "api/profile/wissen/\(id)/\(action)", timeout: 120)
    }

    /// A recording (WAV) for speaker recognition; the Spark wants a fresh code for it.
    func addVoice(wav: Data, code: String) async throws -> Int {
        let boundary = "spark-" + UUID().uuidString
        var r = request("api/profile/voice", method: "POST")
        r.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        r.setValue(code, forHTTPHeaderField: "X-Speech-Code")
        r.timeoutInterval = 90
        var body = Data()
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"stimme.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8))
        body.append(wav)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        r.httpBody = body
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return (Self.object(data)["samples"] as? NSNumber)?.intValue ?? 0
    }
}
