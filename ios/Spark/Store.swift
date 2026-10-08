import Foundation
import Security

/// Where the Spark is and the device key the panel gave this iPhone.
/// The key lives in the keychain, only on this iPhone, readable after the first unlock
/// (so "Hey Siri, Frag Spark" works while the phone is locked). It is never shown or logged.
enum Store {
    private static let service = "speech-spark"
    private static let account = "device-key"
    private static let defaults = UserDefaults.standard

    static var baseURL: URL? {
        get { defaults.string(forKey: "base").flatMap(URL.init(string:)) }
        set { defaults.set(newValue?.absoluteString, forKey: "base") }
    }

    static var profile: String {
        get { defaults.string(forKey: "profile") ?? "" }
        set { defaults.set(newValue, forKey: "profile") }
    }

    /// Language for the speech recognition, as the panel sets it ("auto", "German", ...).
    static var language: String {
        get { defaults.string(forKey: "language") ?? "auto" }
        set { defaults.set(newValue, forKey: "language") }
    }

    static var key: String? {
        get {
            var q = query
            q[kSecReturnData as String] = true
            q[kSecMatchLimit as String] = kSecMatchLimitOne
            var out: CFTypeRef?
            guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
            return String(data: data, encoding: .utf8)
        }
        set {
            SecItemDelete(query as CFDictionary)
            guard let value = newValue, let data = value.data(using: .utf8) else { return }
            var q = query
            q[kSecValueData as String] = data
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(q as CFDictionary, nil)
        }
    }

    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    static var paired: Bool { baseURL != nil && key != nil }

    static func forget() {
        key = nil
        baseURL = nil
        profile = ""
    }
}
