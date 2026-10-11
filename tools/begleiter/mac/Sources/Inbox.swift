import AppKit

/// Part "inbox" (Vom Handy auf den Mac): the poll brings things sent to this Mac in the panel.
///  text -> clipboard + notification; link -> "Link öffnen?" [Öffnen] [Kopieren] [Nein] (only http/https open);
///  file -> ~/Downloads/Vom Spark/<name> (never overwritten), notification with "Ordner öffnen".
/// Each id is handled once (remembered across restarts), then POST /api/desk/inbox/done (also for refused links).
@MainActor
final class InboxCenter {
    static let shared = InboxCenter()
    static let seenKey = "inbox.seen"
    static let doneKey = "inbox.pendingDone"
    static let folderName = "Vom Spark"

    private var queue: [InboxItem] = []
    private var seen: SeenIDs
    /// ids whose "done" did not reach the Spark yet (sent again with the next poll)
    private var pendingDone: [String]
    private var working = false

    init() {
        seen = SeenIDs(UserDefaults.standard.stringArray(forKey: Self.seenKey) ?? [], limit: 500)
        pendingDone = Array((UserDefaults.standard.stringArray(forKey: Self.doneKey) ?? []).suffix(100))
    }

    static var folder: URL {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Downloads", isDirectory: true)
        return downloads.appendingPathComponent(folderName, isDirectory: true)
    }

    static func revealFolder() {
        let f = folder
        try? FileManager.default.createDirectory(at: f, withIntermediateDirectories: true)
        NSWorkspace.shared.open(f)
    }

    /// new items from the poll
    func take(_ items: [InboxItem]) {
        retryDone()
        for i in items where !seen.contains(i.id) && !queue.contains(where: { $0.id == i.id }) {
            queue.append(i)
        }
        next()
    }

    func clear() {
        queue = []
    }

    private func remember(_ id: String) {
        seen.add(id)
        UserDefaults.standard.set(seen.list, forKey: Self.seenKey)
    }

    private func forget(_ id: String) {
        var list = seen.list
        list.removeAll { $0 == id }
        seen = SeenIDs(list, limit: 500)
        UserDefaults.standard.set(seen.list, forKey: Self.seenKey)
    }

    private func next() {
        guard !working, !queue.isEmpty else { return }
        let item = queue.removeFirst()
        guard !seen.contains(item.id) else { return next() }
        remember(item.id)                     // before anything happens: never twice
        working = true
        Task { @MainActor in
            await self.handle(item)
            self.working = false
            self.next()
        }
    }

    private func handle(_ item: InboxItem) async {
        let model = AppModel.shared
        guard model.part("inbox"), let client = model.client else {
            forget(item.id)
            return
        }
        switch item.kind {
        case .text:
            Clip.put(item.text)
            Notifier.plain(title: "Vom Spark", body: "Text liegt in der Zwischenablage")
        case .link:
            link(item.text)
        case .file:
            let ok = await file(item, client: client)
            if !ok {
                forget(item.id)               // nothing was delivered: try again with the next poll
                return
            }
        }
        await done(item.id, client: client)
    }

    private func link(_ raw: String) {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        let url = InboxItem.openable(raw)
        a.messageText = url == nil ? "Link vom Spark" : "Link öffnen?"
        a.informativeText = String(raw.prefix(2000))
            + (url == nil ? "\n\nNur http- und https-Adressen öffnet der Begleiter." : "")
        if url != nil { a.addButton(withTitle: "Öffnen") }
        a.addButton(withTitle: "Kopieren")
        let no = a.addButton(withTitle: "Nein")
        no.keyEquivalent = "\u{1b}"
        a.window.level = .floating
        let r = a.runModal()
        let first = NSApplication.ModalResponse.alertFirstButtonReturn
        let second = NSApplication.ModalResponse.alertSecondButtonReturn
        if let url {
            if r == first { NSWorkspace.shared.open(url) } else if r == second { Clip.put(raw) }
        } else if r == first {
            Clip.put(raw)
        }
    }

    /// false when it should be tried again later (the Spark or the network was not there)
    private func file(_ item: InboxItem, client: SparkClient) async -> Bool {
        if let s = item.size, s > InboxItem.maxFile {
            Notifier.plain(title: "Vom Spark", body: "Die Datei ist zu groß (höchstens 20 MB).")
            return true
        }
        let fm = FileManager.default
        let dir = Self.folder
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        } catch {
            Notifier.plain(title: "Vom Spark", body: "Der Ordner „Downloads/Vom Spark“ ließ sich nicht anlegen.")
            return true
        }
        let name = InboxName.unique(InboxName.sanitize(item.name)) { n in
            fm.fileExists(atPath: dir.appendingPathComponent(n).path)
        }
        let dest = dir.appendingPathComponent(name)
        do {
            try await client.inboxFile(id: item.id, to: dest)
        } catch {
            let m = AppModel.shared.absorb(error)
            if let p = error as? SparkProblem {
                switch p {
                case .offline, .busy, .notaus, .unknownDevice: return false
                default: break
                }
            } else {
                return false
            }
            Notifier.plain(title: "Vom Spark", body: "Die Datei kam nicht an: " + m)
            return true
        }
        Notifier.inboxFile(name: name)
        return true
    }

    private func done(_ id: String, client: SparkClient) async {
        do {
            try await client.inboxDone(id: id)
        } catch {
            AppModel.shared.absorb(error)
            if !pendingDone.contains(id) { pendingDone.append(id) }
            UserDefaults.standard.set(Array(pendingDone.suffix(100)), forKey: Self.doneKey)
        }
    }

    private func retryDone() {
        guard !pendingDone.isEmpty, let client = AppModel.shared.client else { return }
        let ids = pendingDone
        pendingDone = []
        UserDefaults.standard.set(pendingDone, forKey: Self.doneKey)
        Task { @MainActor in
            for id in ids { await self.done(id, client: client) }
        }
    }
}
