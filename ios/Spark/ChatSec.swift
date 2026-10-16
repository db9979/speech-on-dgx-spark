import CryptoKit
import Foundation
import Security
import UIKit

// Private Chats on the iPhone (chatsec.py, the same boxes as chatsec.js in the browser and the Android app).
// This iPhone makes its own key (ECDH P-256), in the Secure Enclave when there is one, else in this app's keychain
// (never in a shared group, never synced). Only the public half goes to the Spark. A message is a box: the payload
// JSON under a fresh AES-256-GCM key (aad = the chat's id), that key wrapped for every current device of both people
// (HKDF-SHA256 over ECDH, info "spark-e2e-v1|chat|from|to"). Photos, files and voice go as nonce + AES-GCM under
// their own file key, which travels inside the payload. What comes out of a box is data: only the known fields.

/// One device key of a private chat (GET /api/chats/keys?id=…).
struct ChatKey: Hashable {
    let id: String
    var uid = ""
    var pub = ""
    var kind = ""
    var t = 0
    var gone = false
}

/// One of this profile's own device keys (GET /api/chats/keys): "want" is a new one waiting for the history.
struct OwnKey: Identifiable, Hashable {
    let id: String
    var kind = ""
    var t = 0
    var want = false
    var pub = ""
}

/// What a box holds: the text and maybe an attachment with its file key.
struct ChatBoxContent: Hashable {
    struct Attachment: Hashable {
        var kind = "file"
        var key = ""
        var name = ""
        var mime = ""
        var size = 0
        var secs = 0
        var w = 0
        var h = 0
    }

    var text = ""
    var att: Attachment?
}

@MainActor
final class ChatSec {
    static let shared = ChatSec()

    private enum Priv {
        case enclave(SecureEnclave.P256.KeyAgreement.PrivateKey)
        case soft(P256.KeyAgreement.PrivateKey)

        func shared(with pub: P256.KeyAgreement.PublicKey) throws -> SharedSecret {
            switch self {
            case .enclave(let k): return try k.sharedSecretFromKeyAgreement(with: pub)
            case .soft(let k): return try k.sharedSecretFromKeyAgreement(with: pub)
            }
        }
    }

    private struct Me {
        let kid: String
        let pub: String
        let priv: Priv
    }

    private var me: Me?
    private(set) var own: [OwnKey] = []
    private var keys: [String: [ChatKey]] = [:]
    private var opened: [String: ChatBoxContent] = [:]

    var kid: String? { me?.kid }

    // ---------------------------------------------------------------- this iPhone's key (keychain, per Spark and profile)
    private var slot: String { "chatsec|" + (Store.baseURL?.host ?? "") + "|" + Store.profile }

    private func query(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "spark.chatsec",
         kSecAttrAccount as String: account]
    }

    private func readRecord() -> [String: Any]? {
        var q = query(slot)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private func writeRecord(_ rec: [String: Any]?) {
        SecItemDelete(query(slot) as CFDictionary)
        guard let rec, let data = try? JSONSerialization.data(withJSONObject: rec) else { return }
        var q = query(slot)
        q[kSecValueData as String] = data
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(q as CFDictionary, nil)
    }

    private func load(_ rec: [String: Any]) -> Me? {
        guard let kid = rec["kid"] as? String, let pub = rec["pub"] as? String,
              let raw = (rec["key"] as? String).flatMap({ Data(base64Encoded: $0) }) else { return nil }
        if rec["se"] as? Bool == true {
            guard let k = try? SecureEnclave.P256.KeyAgreement.PrivateKey(dataRepresentation: raw) else { return nil }
            return Me(kid: kid, pub: pub, priv: .enclave(k))
        }
        guard let k = try? P256.KeyAgreement.PrivateKey(rawRepresentation: raw) else { return nil }
        return Me(kid: kid, pub: pub, priv: .soft(k))
    }

    /// Unpairing: this iPhone's key for private chats goes too (the Spark keeps only its public half).
    func forget() {
        writeRecord(nil)
        me = nil
        own = []
        keys = [:]
        opened = [:]
    }

    func ownKeys() async throws -> [OwnKey] {
        guard let api = SparkAPI.current else { return [] }
        let d = try await api.get("api/chats/keys")
        own = (d["keys"] as? [[String: Any]] ?? []).prefix(20).compactMap { x in
            guard let id = x["id"] as? String, id.count == 12 else { return nil }
            return OwnKey(id: id, kind: String((x["kind"] as? String ?? "").prefix(10)), t: (x["t"] as? NSNumber)?.intValue ?? 0,
                          want: x["want"] as? Bool ?? false, pub: String((x["pub"] as? String ?? "").prefix(100)))
        }
        return own
    }

    /// This iPhone's key while the Spark still lists it; nil when it has none.
    func device() async throws -> String? {
        let list = try await ownKeys()
        if let m = me, list.contains(where: { $0.id == m.kid }) { return m.kid }
        if let rec = readRecord(), let m = load(rec), list.contains(where: { $0.id == m.kid }) {
            me = m
            return m.kid
        }
        if readRecord() != nil { writeRecord(nil) }   // removed on another device: this iPhone starts anew
        me = nil
        return nil
    }

    /// A new key for this iPhone, like a new device for the Spark: the profile's code when it has a second step.
    func addDevice(code: String) async throws {
        guard let api = SparkAPI.current else { return }
        let priv: Priv, raw: Data, se: Bool, pub: String
        if SecureEnclave.isAvailable, let k = try? SecureEnclave.P256.KeyAgreement.PrivateKey() {
            priv = .enclave(k)
            raw = k.dataRepresentation
            se = true
            pub = k.publicKey.x963Representation.base64EncodedString()
        } else {
            let k = P256.KeyAgreement.PrivateKey()
            priv = .soft(k)
            raw = k.rawRepresentation
            se = false
            pub = k.publicKey.x963Representation.base64EncodedString()
        }
        var r = api.request("api/chats/keys", method: "POST")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["pub": pub, "kind": "iphone"])
        let (data, response) = try await SparkAPI.confirmed(r, code: code)
        try SparkAPI.check(data, response)
        let d = SparkAPI.object(data)
        guard let kid = d["id"] as? String, kid.count == 12 else { throw SparkError(message: String(localized: "Der Spark hat den Schlüssel nicht angenommen.")) }
        writeRecord(["kid": kid, "pub": pub, "se": se, "key": raw.base64EncodedString()])
        me = Me(kid: kid, pub: pub, priv: priv)
        opened = [:]
        _ = try? await ownKeys()
    }

    func removeDevice(_ id: String) async throws {
        guard let api = SparkAPI.current else { return }
        _ = try await api.post("api/chats/keys/remove", ["id": id])
        if me?.kid == id {
            writeRecord(nil)
            me = nil
            opened = [:]
        }
        keys = [:]
        _ = try? await ownKeys()
    }

    func chatKeys(_ cid: String, fresh: Bool = false) async throws -> [ChatKey] {
        if !fresh, let k = keys[cid] { return k }
        guard let api = SparkAPI.current else { return [] }
        var c = URLComponents(url: api.base.appendingPathComponent("api/chats/keys"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "id", value: cid)]
        let d = try await api.get("api/chats/keys", url: c.url)
        let list: [ChatKey] = (d["keys"] as? [[String: Any]] ?? []).prefix(200).compactMap { x in
            guard let id = x["id"] as? String, let pub = x["pub"] as? String else { return nil }
            return ChatKey(id: id, uid: x["uid"] as? String ?? "", pub: pub, kind: x["kind"] as? String ?? "",
                           t: (x["t"] as? NSNumber)?.intValue ?? 0, gone: x["gone"] != nil)
        }
        keys[cid] = list
        return list
    }

    // ---------------------------------------------------------------- boxes
    private static func random(_ n: Int) -> Data {
        var d = Data(count: n)
        _ = d.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, n, $0.baseAddress!) }
        return d
    }

    private static func b64(_ s: Any?) -> Data? { (s as? String).flatMap { Data(base64Encoded: $0) } }

    private func wrapKey(_ pub: String, _ cid: String, _ from: String, _ to: String, _ salt: Data) throws -> SymmetricKey {
        guard let m = me, let raw = Data(base64Encoded: pub) else { throw SparkError(message: String(localized: "Schlüssel fehlt.")) }
        let peer = try P256.KeyAgreement.PublicKey(x963Representation: raw)
        return try m.priv.shared(with: peer).hkdfDerivedSymmetricKey(using: SHA256.self, salt: salt,
                                                                     sharedInfo: Data("spark-e2e-v1|\(cid)|\(from)|\(to)".utf8), outputByteCount: 32)
    }

    /// AES-GCM as WebCrypto writes it: the ciphertext with its 16-byte tag at the end.
    private static func seal(_ data: Data, _ key: SymmetricKey, _ nonce: Data, aad: Data? = nil) throws -> Data {
        let n = try AES.GCM.Nonce(data: nonce)
        let box = try aad.map { try AES.GCM.seal(data, using: key, nonce: n, authenticating: $0) } ?? AES.GCM.seal(data, using: key, nonce: n)
        return box.ciphertext + box.tag
    }

    private static func open(_ data: Data, _ key: SymmetricKey, _ nonce: Data, aad: Data? = nil) throws -> Data {
        guard data.count >= 16 else { throw SparkError(message: "bad box") }
        let box = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: nonce), ciphertext: data.prefix(data.count - 16), tag: data.suffix(16))
        if let aad { return try AES.GCM.open(box, using: key, authenticating: aad) }
        return try AES.GCM.open(box, using: key)
    }

    private func box(_ cid: String, _ payload: [String: Any], _ keys: [ChatKey]) throws -> [String: Any] {
        guard let m = me else { throw SparkError(message: String(localized: "Dieses Gerät hat noch keinen Schlüssel für private Chats.")) }
        let content = SymmetricKey(size: .bits256)
        let raw = content.withUnsafeBytes { Data($0) }
        let iv = Self.random(12)
        let ct = try Self.seal(try JSONSerialization.data(withJSONObject: payload), content, iv, aad: Data(cid.utf8))
        var k: [String: Any] = [:]
        for x in keys where !x.gone {
            let s = Self.random(16), wi = Self.random(12)
            let w = try Self.seal(raw, try wrapKey(x.pub, cid, m.kid, x.id, s), wi)
            k[x.id] = ["s": s.base64EncodedString(), "i": wi.base64EncodedString(), "w": w.base64EncodedString()]
        }
        return ["v": 1, "f": m.kid, "iv": iv.base64EncodedString(), "ct": ct.base64EncodedString(), "k": k]
    }

    /// The content key of a box for this iPhone and who sent it; nil when it is not for this iPhone (sent before it
    /// was added) or not from a known key. {"b": …}: wrapped later by an older device of the same person.
    private func contentKey(_ cid: String, f: String, _ keys: [ChatKey], _ w: [String: Any]) throws -> (ChatKey, Data)? {
        guard let m = me, let snd = keys.first(where: { $0.id == f }) else { return nil }
        var by = snd
        if let b = w["b"] as? String {
            guard let mine = keys.first(where: { $0.id == m.kid }), let o = keys.first(where: { $0.id == b }), o.uid == mine.uid else { return nil }
            by = o
        }
        guard let s = Self.b64(w["s"]), let i = Self.b64(w["i"]), let ww = Self.b64(w["w"]) else { return nil }
        return (snd, try Self.open(ww, try wrapKey(by.pub, cid, by.id, m.kid, s), i))
    }

    private func unbox(_ cid: String, from: String, _ box: [String: Any], _ keys: [ChatKey]) -> ChatBoxContent? {
        guard let m = me, let w = (box["k"] as? [String: Any])?[m.kid] as? [String: Any], let f = box["f"] as? String,
              let got = try? contentKey(cid, f: f, keys, w), got.0.uid == from,
              let iv = Self.b64(box["iv"]), let ct = Self.b64(box["ct"]),
              let pt = try? Self.open(ct, SymmetricKey(data: got.1), iv, aad: Data(cid.utf8)),
              let p = (try? JSONSerialization.jsonObject(with: pt)) as? [String: Any] else { return nil }
        // what came out of a box is data from outside: only the known fields, as plain values
        var out = ChatBoxContent(text: String((p["t"] as? String ?? "").prefix(4000)))
        if let a = p["a"] as? [String: Any], let kind = a["kind"] as? String, ["photo", "file", "voice"].contains(kind),
           let key = a["k"] as? String, Data(base64Encoded: key)?.count == 32 {
            func n(_ k: String) -> Int { max(0, min(1 << 31, (a[k] as? NSNumber)?.intValue ?? 0)) }
            out.att = .init(kind: kind, key: key, name: String((a["name"] as? String ?? "").prefix(200)),
                            mime: String((a["mime"] as? String ?? "").prefix(100)), size: n("size"), secs: n("secs"), w: n("w"), h: n("h"))
        }
        return out
    }

    private static func dict(_ d: Data?) -> [String: Any]? {
        d.flatMap { (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] }
    }

    /// Before the chat is drawn: every box becomes text (and an attachment) for this iPhone. false: this iPhone has
    /// no key yet, or the keys cannot be fetched.
    func prepare(_ cid: String, _ lines: inout [ChatLine]) async -> Bool {
        if me == nil || !own.contains(where: { $0.id == me?.kid }) { _ = try? await device() }
        guard me != nil, var list = try? await chatKeys(cid) else {
            for i in lines.indices where lines[i].box != nil { lock(&lines[i]) }
            return false
        }
        let senders = lines.compactMap { Self.dict($0.box)?["f"] as? String }
        if senders.contains(where: { f in !list.contains { $0.id == f } })
            || lines.contains(where: { $0.kind == "sys" && ($0.sys == "newkey" || $0.sys == "keygone") }) {
            list = (try? await chatKeys(cid, fresh: true)) ?? list
        }
        for i in lines.indices {
            guard let b = Self.dict(lines[i].box), !lines[i].gone else { continue }
            let ck = cid + "|" + lines[i].id
            var p = opened[ck]
            if p == nil {
                p = unbox(cid, from: lines[i].from, b, list)
                if let p { opened[ck] = p }   // not yet: maybe the history comes
            }
            show(&lines[i], p)
        }
        for i in lines.indices {
            guard let q = lines[i].reply, !q.gone else { continue }
            if let p = opened[cid + "|" + q.id] {
                lines[i].reply?.text = p.text
                lines[i].reply?.kind = p.att?.kind ?? "text"
            }
        }
        return true
    }

    private func lock(_ l: inout ChatLine) { show(&l, nil) }

    private func show(_ l: inout ChatLine, _ p: ChatBoxContent?) {
        l.box = nil
        guard let p else {
            l.kind = "text"
            l.locked = true
            l.text = String(localized: "🔒 Auf diesem Gerät nicht lesbar (vor seinem Eintragen geschickt).")
            return
        }
        l.text = p.text
        if let a = p.att {
            l.kind = a.kind
            l.fileKey = a.key
            l.media = ChatMedia(w: a.w, h: a.h, secs: a.secs, size: a.size,
                                ext: String((a.name.split(separator: ".").last.map(String.init) ?? "").prefix(8)), name: a.name)
        } else {
            l.kind = "text"
        }
    }

    // ---------------------------------------------------------------- sending
    /// A box for every current device of both; a new device of the other one since the last fetch: fetch, box again, once.
    private func sendBox(_ cid: String, _ payload: [String: Any], reply: String, blob: Data? = nil) async throws {
        guard let api = SparkAPI.current else { return }
        if me == nil { _ = try await device() }
        guard me != nil else { throw SparkError(message: String(localized: "Dieses Gerät hat noch keinen Schlüssel für private Chats.")) }
        for i in 0..<2 {
            let b = try box(cid, payload, try await chatKeys(cid, fresh: i > 0))
            do {
                if let blob {
                    var c = URLComponents(url: api.base.appendingPathComponent("api/chats/media"), resolvingAgainstBaseURL: false)!
                    c.queryItems = [URLQueryItem(name: "id", value: cid), URLQueryItem(name: "kind", value: "box"),
                                    URLQueryItem(name: "reply", value: reply)]
                    var r = api.request("api/chats/media", method: "POST")
                    r.url = c.url
                    r.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
                    r.httpBody = try JSONSerialization.data(withJSONObject: b) + Data("\n".utf8) + blob
                    let (data, response) = try await URLSession.shared.data(for: r)
                    try SparkAPI.check(data, response)
                } else {
                    _ = try await api.post("api/chats/send", ["id": cid, "text": "", "reply": reply, "box": b])
                }
                return
            } catch let e as SparkError where i == 0 && e.message.contains("neues Gerät") {
                continue
            }
        }
    }

    func send(_ cid: String, text: String, reply: String) async throws {
        try await sendBox(cid, ["t": text], reply: reply)
    }

    /// A photo (drawn anew, at most 2048 px: no place or camera data), a file or a voice message, under its own key.
    func upload(_ cid: String, kind: String, data: Data, name: String = "", mime: String = "", secs: Int = 0, reply: String) async throws {
        var kind = kind, data = data, mime = mime, w = 0, h = 0
        if kind == "photo" {
            if let img = UIImage(data: data) {
                let f = min(1, 2048 / max(img.size.width, img.size.height, 1))
                let size = CGSize(width: (img.size.width * f).rounded(), height: (img.size.height * f).rounded())
                let fmt = UIGraphicsImageRendererFormat.default()
                fmt.scale = 1
                let out = UIGraphicsImageRenderer(size: size, format: fmt).image { _ in img.draw(in: CGRect(origin: .zero, size: size)) }
                if let jpeg = out.jpegData(compressionQuality: 0.85) {
                    data = jpeg
                    mime = "image/jpeg"
                    w = Int(size.width)
                    h = Int(size.height)
                } else { kind = "file" }
            } else { kind = "file" }
        }
        let fk = SymmetricKey(size: .bits256)
        guard let sealed = try AES.GCM.seal(data, using: fk).combined else { throw SparkError(message: String(localized: "Verschlüsseln ging nicht.")) }
        let att: [String: Any] = ["kind": kind, "k": fk.withUnsafeBytes { Data($0) }.base64EncodedString(),
                                  "name": kind == "file" ? String(name.prefix(200)) : "", "mime": String(mime.prefix(100)),
                                  "size": data.count, "secs": secs, "w": w, "h": h]
        try await sendBox(cid, ["t": "", "a": att], reply: reply, blob: sealed)
    }

    /// The bytes of a private attachment: the Spark keeps them as nonce + AES-GCM under the file key from the box.
    static func openMedia(_ data: Data, key: String) throws -> Data {
        guard let k = Data(base64Encoded: key), k.count == 32 else { throw SparkError(message: "bad key") }
        return try AES.GCM.open(AES.GCM.SealedBox(combined: data), using: SymmetricKey(data: k))
    }

    /// Starts (or opens) the private chat with someone; this iPhone needs its key first.
    func start(with to: String) async throws -> String {
        guard let api = SparkAPI.current else { return "" }
        if me == nil { _ = try await device() }
        guard me != nil else { throw SparkError(message: String(localized: "Dieses Gerät hat noch keinen Schlüssel für private Chats.")) }
        return try await api.post("api/chats/private", ["to": to])["id"] as? String ?? ""
    }

    // ---------------------------------------------------------------- Sicherheitsnummer and device code
    /// SHA-512 over both people's current public keys, 12 blocks of 5 digits (as chatsec.js).
    func number(_ cid: String) async throws -> String {
        let list = try await chatKeys(cid, fresh: true)
        var by: [String: [String]] = [:]
        for k in list where !k.gone { by[k.uid, default: []].append(k.pub) }
        let s = by.keys.sorted().map { u in u + ":" + by[u]!.sorted().joined(separator: ",") }.joined(separator: "|")
        let h = Array(SHA512.hash(data: Data("spark-e2e-v1|\(cid)|\(s)".utf8)))
        return (0..<12).map { i in
            var v = 0
            for j in 0..<5 { v = (v * 256 + Int(h[i * 5 + j])) % 100000 }
            return String(format: "%05d", v)
        }.joined(separator: " ")
    }

    /// The code both devices show for a new device: from its public key only.
    static func code(_ pub: String) -> String {
        let h = Array(SHA256.hash(data: Data("spark-e2e-v1|device|\(pub)".utf8)))
        let a = Array("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        return String((0..<6).map { a[Int(h[$0]) % 32] })
    }

    static func seenKey(_ cid: String) -> String { "cs-ok:" + Store.profile + ":" + cid }

    /// This iPhone's own entry: a new one waiting for the history shows its code on the chat.
    var mine: OwnKey? { own.first { $0.id == me?.kid } }

    /// A new device of the same person that this (older) iPhone can hand the history to.
    var newDevice: OwnKey? {
        guard let m = mine, !m.want else { return nil }
        return own.first { $0.want && $0.id != m.id && $0.t >= m.t && !$0.pub.isEmpty }
    }

    // ---------------------------------------------------------------- the history for a new device (Wahl 2)
    /// Wraps each content key this iPhone can open once more for the new device; returns how many.
    func share(to nk: OwnKey, chats: [String], progress: (Int) -> Void) async throws -> Int {
        guard let api = SparkAPI.current, let m = me else { return 0 }
        var n = 0, done = 0
        for cid in chats {
            var c = URLComponents(url: api.base.appendingPathComponent("api/chats/share"), resolvingAgainstBaseURL: false)!
            c.queryItems = [URLQueryItem(name: "id", value: cid), URLQueryItem(name: "by", value: m.kid), URLQueryItem(name: "new", value: nk.id)]
            let d = try await api.get("api/chats/share", url: c.url)
            let list = try await chatKeys(cid, fresh: true)
            var wraps: [String: Any] = [:]
            func flush() async throws {
                guard !wraps.isEmpty else { return }
                let r = try await api.post("api/chats/share", ["id": cid, "by": m.kid, "new": nk.id, "wraps": wraps])
                n += (r["added"] as? NSNumber)?.intValue ?? 0
                wraps = [:]
            }
            for it in (d["items"] as? [[String: Any]] ?? []) {
                guard let mid = it["id"] as? String, let f = it["f"] as? String, let w = it["w"] as? [String: Any],
                      let got = try? contentKey(cid, f: f, list, w), got.0.uid == (it["from"] as? String ?? "") else { continue }
                // only what this iPhone can open and really comes from that person
                let s = Self.random(16), i = Self.random(12)
                let ww = try Self.seal(got.1, try wrapKey(nk.pub, cid, m.kid, nk.id, s), i)
                wraps[mid] = ["s": s.base64EncodedString(), "i": i.base64EncodedString(), "w": ww.base64EncodedString()]
                if wraps.count >= 300 { try await flush() }
            }
            try await flush()
            done += 1
            progress(done)
        }
        _ = try await api.post("api/chats/share/done", ["new": nk.id, "n": n])
        _ = try? await ownKeys()
        return n
    }
}

extension SparkAPI {
    /// A GET that answers with a JSON object (url: the same path with its query).
    func get(_ path: String, url: URL? = nil) async throws -> [String: Any] {
        var r = request(path)
        if let url { r.url = url }
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return Self.object(data)
    }
}
