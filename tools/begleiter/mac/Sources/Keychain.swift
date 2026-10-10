import Foundation
import Security

/// The pairing in the login keychain: one generic password, service "Spark Begleiter", account = the Spark's base,
/// password = the device key. Nothing of it is ever written to a file or a log.
enum Keychain {
    static let service = "Spark Begleiter"

    static func load() -> (base: String, key: String)? {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnAttributes as String: true,
            kSecReturnData as String: true,
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let d = out as? [String: Any],
              let base = d[kSecAttrAccount as String] as? String,
              let data = d[kSecValueData as String] as? Data,
              let key = String(data: data, encoding: .utf8), !key.isEmpty else {
            return nil
        }
        return (base, key)
    }

    @discardableResult
    static func save(base: String, key: String) -> Bool {
        delete()
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: base,
            kSecAttrLabel as String: service,
            kSecAttrDescription as String: "Schlüssel des Spark-Begleiters",
            kSecValueData as String: Data(key.utf8),
        ]
        return SecItemAdd(q as CFDictionary, nil) == errSecSuccess
    }

    static func delete() {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]
        // the file keychain may delete one match per call
        for _ in 0..<10 {
            if SecItemDelete(q as CFDictionary) != errSecSuccess { break }
        }
    }
}
