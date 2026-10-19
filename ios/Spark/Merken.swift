import CryptoKit
import Foundation
import SwiftUI

/// „Apps merken sich den letzten Stand“ (appmerken.py on the Spark, admin switch chat.app_cache; Dominik 2026-10-17).
/// The app keeps the last answer of a few pages for its profile on this iPhone and shows it at once the next time,
/// with the note „Stand 16:05 · wird aktualisiert …“, until the Spark has answered: what the profile may (hello), the
/// conversations (the 20 newest with their last 50 messages), the chats and the last page of up to 20 of them, the
/// own settings, the functions and the numbers on the tiles of „Meine Sachen“ (only how many, never a name or a file),
/// the appointments of four weeks around today, the newest 50 mails of the inbox (sender, subject, time) and up to 20
/// mails opened last with their text (plan kalender-mail 1b; each only while its function is released).
///
/// Only while the Spark says so (hello "keep": the function released for the profile); otherwise everything kept is
/// deleted at once. Unpairing, another key (another profile or another Spark) delete it too. Never kept: the key and
/// any code, the admin areas (AdminSession), private and vanishing chats, files and pictures. The files lie in the
/// app's own Application Support with data protection „complete“ (unreadable while the iPhone is locked) and are
/// never part of an iCloud or computer backup.
enum Merken {
    /// one answer at most this big; a bigger one is not kept (the conversations are cut down first)
    static let maxBytes = 1_500_000
    static let convos = 20
    static let messages = 50
    static let chatPages = 20
    /// opened mails kept with their text (E-Mail, KalenderPost.swift), the newest ones
    static let mailPages = 20
    /// from here a page counts as slow and is reported once (appmerken.SLOW_MS on the Spark)
    static let slowMs = 2000
    /// fetching in the background on coming to the front: at most this often
    static let prefetchEvery: TimeInterval = 5 * 60

    private static let onKey = "merken.on"
    private static let names = try! NSRegularExpression(pattern: "^[a-z][a-z0-9-]{0,40}$")

    /// What the Spark said last (hello "keep"); before the first answer nothing is kept or shown.
    static var on: Bool { UserDefaults.standard.bool(forKey: onKey) }

    /// The Spark's answer to hello: keep from now on, or delete everything kept.
    static func allow(_ keep: Bool) {
        UserDefaults.standard.set(keep, forKey: onKey)
        if !keep { forget() }
    }

    /// Everything kept, of every profile and Spark (unpairing, the function off).
    static func forget() {
        guard let root else { return }
        try? FileManager.default.removeItem(at: root)
    }

    private static var root: URL? {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("Merken", isDirectory: true)
    }

    /// The folder of this pairing: a name from the Spark's address and the key (never the key itself), so another
    /// profile or another Spark never sees what this one kept, and what an earlier pairing kept is deleted.
    private static var folder: URL? {
        guard let root, let base = Store.baseURL, let key = Store.key else { return nil }
        let h = SHA256.hash(data: Data((base.absoluteString + "\n" + key).utf8))
        let name = h.prefix(12).map { String(format: "%02x", $0) }.joined()
        let dir = root.appendingPathComponent(name, isDirectory: true)
        let fm = FileManager.default
        if !fm.fileExists(atPath: dir.path) {
            try? fm.removeItem(at: root)   // another pairing kept something: gone before this one starts
            do {
                try fm.createDirectory(at: dir, withIntermediateDirectories: true,
                                       attributes: [.protectionKey: FileProtectionType.complete])
                var r = root
                var v = URLResourceValues()
                v.isExcludedFromBackup = true
                try r.setResourceValues(v)
            } catch { return nil }
        }
        return dir
    }

    private static func file(_ name: String) -> URL? {
        guard names.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) != nil else { return nil }
        return folder?.appendingPathComponent(name + ".json")
    }

    /// Keeps the Spark's answer for a page (only while on; too big answers are not kept).
    static func keep(_ name: String, _ data: Data) {
        guard on, Demo.scene == nil, data.count <= maxBytes, let url = file(name) else { return }
        try? data.write(to: url, options: [.atomic, .completeFileProtection])
        if name.hasPrefix("chat-") { tidy("chat-", chatPages) }
        if name.hasPrefix("mail-") { tidy("mail-", mailPages) }
    }

    /// What was kept for a page and when; nil when nothing (or the function is off).
    static func get(_ name: String) -> (data: Data, at: Date)? {
        guard on, Demo.scene == nil, let url = file(name), let data = try? Data(contentsOf: url) else { return nil }
        let at = (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? Date()
        return (data, at)
    }

    /// The name of a chat's kept page ("chat-" and the chat's id from the Spark, only letters and digits).
    static func name(chat id: String) -> String? {
        id.range(of: "^[a-z0-9]{1,34}$", options: .regularExpression) != nil ? "chat-" + id : nil
    }

    /// Every kept page of one kind ("mail-"): the function was switched off for the profile.
    static func dropAll(_ prefix: String) {
        tidy(prefix, 0)
    }

    static func drop(_ name: String) {
        guard let url = file(name) else { return }
        try? FileManager.default.removeItem(at: url)
    }

    /// At most `most` pages of one kind (chats, opened mails): the ones looked at longest ago go first.
    private static func tidy(_ prefix: String, _ most: Int) {
        guard let dir = folder, let all = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: [.contentModificationDateKey]) else { return }
        let pages = all.filter { $0.lastPathComponent.hasPrefix(prefix) }.sorted {
            let a = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let b = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return a > b
        }
        for old in pages.dropFirst(most) { try? FileManager.default.removeItem(at: old) }
    }

    // ---------------------------------------------------------------- the pages' own kinds
    /// The answer to hello: follow its "keep" and keep it for the next start.
    static func saw(_ a: Allowed) {
        allow(a.keep)
        if let d = try? JSONEncoder().encode(a) { keep("hello", d) }
    }

    /// The last hello, to draw the page before the Spark answers: never what starts the microphone, push, calls or
    /// writes into the iPhone's Reminders (those wait for the Spark's own answer).
    static func allowed() -> Allowed? {
        guard let k = get("hello"), var a = try? JSONDecoder().decode(Allowed.self, from: k.data) else { return nil }
        a.listen = false; a.act = false; a.proactive = false; a.push = false; a.calls = false; a.ios = false
        return a
    }

    /// The newest conversations with their last messages (the same shape as /api/profile/convos).
    static func keepConvos(_ list: [SavedConvo]) {
        let cut: [[String: Any]] = list.sorted { $0.updated > $1.updated }.prefix(convos).map { c in
            ["id": c.id, "title": c.title, "updated": Int(c.updated.timeIntervalSince1970 * 1000), "msgs": Array(c.msgs.suffix(messages))]
        }
        if let d = try? JSONSerialization.data(withJSONObject: cut) { keep("verlauf", d) }
    }

    static func convoList() -> (list: [SavedConvo], at: Date)? {
        guard let k = get("verlauf") else { return nil }
        return (SparkAPI.convoList(k.data), k.at)
    }

    /// An answer that is a JSON object (the own settings, the functions).
    static func keepObject(_ name: String, _ d: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: d) { keep(name, data) }
    }

    static func object(_ name: String) -> (d: [String: Any], at: Date)? {
        guard let k = get(name), let d = try? JSONSerialization.jsonObject(with: k.data) as? [String: Any] else { return nil }
        return (d, k.at)
    }

    // ---------------------------------------------------------------- slow pages into the Spark's log
    @MainActor private static var reported: [String: Date] = [:]

    /// Runs a page's load and tells the Spark when it took longer than slowMs (once per page in 10 minutes):
    /// only the fixed page word and the milliseconds (appmerken.PAGES), never what was on the page.
    @MainActor
    static func timed<T>(_ page: String, _ work: () async throws -> T) async rethrows -> T {
        let began = Date()
        let r = try await work()
        let ms = Int(Date().timeIntervalSince(began) * 1000)
        if ms >= slowMs, Demo.scene == nil, Date().timeIntervalSince(reported[page] ?? .distantPast) > 600,
           let api = SparkAPI.current {
            reported[page] = Date()
            Task { _ = try? await api.post("api/app/langsam", ["seite": page, "ms": min(ms, 600_000)]) }
        }
        return r
    }

    // ---------------------------------------------------------------- fetching ahead
    @MainActor private static var fetchedAt = Date.distantPast

    /// Coming to the front: the conversations, the chats and the own settings once in the background (at most every
    /// prefetchEvery), so the pages open with a fresh state.
    @MainActor
    static func prefetch(chats: Bool) async {
        guard on, Demo.scene == nil, Date().timeIntervalSince(fetchedAt) >= prefetchEvery, let api = SparkAPI.current else { return }
        fetchedAt = Date()
        if let list = try? await api.convos() { keepConvos(list) }
        if let d = try? await api.profileSettings() { keepObject("einstellungen", d) }
        if let d = try? await api.object("GET", "api/features") { keepObject("funktionen", d) }
        if chats { _ = try? await api.chats() }   // keeps itself (ChatsView.swift)
    }
}

/// While a page waits for the Spark: grey placeholder rows, after a second „Verbinde mit dem Spark …“, after 8 s
/// „Das dauert länger als sonst …“ (the same steps as the panel's laden.js).
struct LadeZeilen: View {
    var rows = 6
    @State private var waited = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if waited >= 1 { LadeNote(text: waited >= 8 ? String(localized: "Das dauert länger als sonst …") : String(localized: "Verbinde mit dem Spark …")) }
            ForEach(0..<rows, id: \.self) { i in
                RoundedRectangle(cornerRadius: 6).fill(Color.secondary.opacity(0.15))
                    .frame(width: CGFloat([0.6, 1, 0.8, 0.5, 0.95, 0.7][i % 6]) * 300, height: 14)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 6)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Lädt …"))
        .task {
            for s in [1, 8] {
                try? await Task.sleep(for: .seconds(s - waited))
                guard !Task.isCancelled else { return }
                waited = s
            }
        }
    }
}

/// The small note on top of a page: „Verbinde …“, or the age of a kept state while it is refreshed.
struct LadeNote: View {
    let text: String

    var body: some View {
        Text(verbatim: text).font(.caption).padding(.horizontal, 10).padding(.vertical, 3)
            .background(Capsule().fill(Color.yellow.opacity(0.18)))
            .overlay(Capsule().stroke(Color.yellow.opacity(0.5)))
            .frame(maxWidth: .infinity)
    }
}

/// A kept state on screen: „Stand 16:05 · wird aktualisiert …“, or that the Spark cannot be reached right now.
struct StandNote: View {
    let at: Date
    let loading: Bool

    var body: some View {
        let time = at.formatted(Calendar.current.isDateInToday(at) ? .dateTime.hour().minute() : .dateTime.day().month().hour().minute())
        LadeNote(text: loading ? String(localized: "Stand \(time) · wird aktualisiert …")
                               : String(localized: "Stand \(time) · Spark gerade nicht erreichbar"))
    }
}

/// A page that could not load and has nothing kept: the reason and „Noch einmal“.
struct LadeFehler: View {
    let title: LocalizedStringKey
    let message: String
    let retry: () async -> Void

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: "wifi.exclamationmark")
        } description: {
            Text(verbatim: message)
        } actions: {
            Button("Noch einmal") { Task { await retry() } }.buttonStyle(.bordered)
        }
    }
}
