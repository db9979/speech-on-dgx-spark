import Foundation
import Security
import UserNotifications

/// Apple carries only "Neue Nachricht vom Spark" and a random id. This extension fetches the text
/// with the app's own key from the Spark (GET /api/iphone/note) and puts it into the banner, so
/// Apple never sees it. Without an answer in time the banner keeps the plain sentence.
final class NotificationService: UNNotificationServiceExtension {
    private let lock = NSLock()
    private var handler: ((UNNotificationContent) -> Void)?
    private var content: UNMutableNotificationContent?
    private var task: URLSessionDataTask?

    override func didReceive(_ request: UNNotificationRequest,
                             withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        let c = (request.content.mutableCopy() as? UNMutableNotificationContent) ?? UNMutableNotificationContent()
        lock.lock(); handler = contentHandler; content = c; lock.unlock()
        // a message from another profile: the notification gets an "Antworten" field (Relay in the app)
        if let k = request.content.userInfo["k"] as? String, k.hasPrefix("msg-") { c.categoryIdentifier = "msg" }
        guard let id = request.content.userInfo["n"] as? String,
              id.range(of: "^[0-9a-f]{16}$", options: .regularExpression) != nil,
              let key = Self.read("device-key"),
              let base = Self.read("base-url").flatMap(URL.init(string:)), base.scheme == "https",
              var parts = URLComponents(url: base.appendingPathComponent("api/iphone/note"), resolvingAgainstBaseURL: false)
        else { finish(); return }
        parts.queryItems = [URLQueryItem(name: "id", value: id)]
        guard let url = parts.url else { finish(); return }
        var r = URLRequest(url: url)
        r.timeoutInterval = 20
        r.setValue(key, forHTTPHeaderField: "X-Speech-Device")
        let t = URLSession.shared.dataTask(with: r) { [weak self] data, response, _ in
            if let data, (response as? HTTPURLResponse)?.statusCode == 200,
               let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let title = d["title"] as? String, !title.isEmpty { c.title = String(title.prefix(200)) }
                if let body = d["body"] as? String, !body.isEmpty {
                    c.body = String(body.prefix(1500))
                    c.userInfo["spark"] = c.body   // the open app says it aloud (Relay)
                }
            }
            self?.finish()
        }
        lock.lock(); task = t; lock.unlock()
        t.resume()
    }

    override func serviceExtensionTimeWillExpire() {
        lock.lock(); let t = task; lock.unlock()
        t?.cancel()
        finish()
    }

    private func finish() {
        lock.lock()
        let h = handler, c = content
        handler = nil
        lock.unlock()
        if let h, let c { h(c) }
    }

    /// The app's key and the Spark's address from the keychain group both share.
    private static func read(_ account: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: "speech-spark",
                                kSecAttrAccount as String: account,
                                kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
