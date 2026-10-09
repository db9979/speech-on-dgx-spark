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
        set {
            defaults.set(newValue?.absoluteString, forKey: "base")
            write("base-url", newValue?.absoluteString)
        }
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
        get { read(account) }
        set { write(account, newValue) }
    }

    /// The keychain group the notification extension can read too ("<team>.<bundle id>.shared");
    /// nil in builds without signing, then the app keeps its own group.
    private static let group: String? = {
        guard let g = Bundle.main.object(forInfoDictionaryKey: "SparkKeychainGroup") as? String,
              !g.hasPrefix("."), !g.contains("$(") else { return nil }
        return g
    }()

    private static func query(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    private static func read(_ account: String) -> String? {
        var q = query(account)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func write(_ account: String, _ value: String?) {
        SecItemDelete(query(account) as CFDictionary)
        guard let value, let data = value.data(using: .utf8) else { return }
        var q = query(account)
        q[kSecValueData as String] = data
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        if let group {
            var shared = q
            shared[kSecAttrAccessGroup as String] = group
            if SecItemAdd(shared as CFDictionary, nil) == errSecSuccess { return }
        }
        SecItemAdd(q as CFDictionary, nil)
    }

    /// Key and address into the shared group, so the notification extension can fetch a message's
    /// text from the Spark (keys stored by older versions sit in the app's own group).
    static func share() {
        guard group != nil, !defaults.bool(forKey: "shared1") else { return }
        if let k = key { key = k }
        if let b = baseURL { baseURL = b }
        defaults.set(true, forKey: "shared1")
    }

    static var paired: Bool { baseURL != nil && key != nil }

    static func forget() {
        key = nil
        baseURL = nil
        profile = ""
    }
}
