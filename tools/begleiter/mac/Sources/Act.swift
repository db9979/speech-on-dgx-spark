import AppKit
import SwiftUI

/// Part "act": the Spark may ask to do something on this Mac. Every single wish needs the person's "Erlauben"
/// (60 s without an answer = Nein). Only a short allowlist can happen at all: open an http(s) address, start a
/// program from the panel's list, media keys, volume keys, lock the screen, show a text. Anything else is refused.
/// The same id never runs twice (also across restarts).
@MainActor
final class ActCenter {
    static let shared = ActCenter()
    static let seenKey = "act.seen"
    static let timeout: TimeInterval = 60

    private var queue: [ActAsk] = []
    private var seen: SeenIDs
    private var showing = false

    init() {
        seen = SeenIDs(UserDefaults.standard.stringArray(forKey: Self.seenKey) ?? [])
    }

    /// new asks from the poll
    func take(_ asks: [ActAsk]) {
        for a in asks where !seen.contains(a.id) && !queue.contains(where: { $0.id == a.id }) {
            queue.append(a)
        }
        next()
    }

    /// part off: forget what waits (the Spark asks again if it still wants it)
    func clear() {
        queue = []
    }

    private func remember(_ id: String) {
        seen.add(id)
        UserDefaults.standard.set(seen.list, forKey: Self.seenKey)
    }

    private func next() {
        guard !showing, !queue.isEmpty else { return }
        let ask = queue.removeFirst()
        guard !seen.contains(ask.id) else { return next() }
        remember(ask.id)                       // before anything happens: never twice
        showing = true
        Task { @MainActor in
            await self.handle(ask)
            self.showing = false
            self.next()
        }
    }

    private func handle(_ ask: ActAsk) async {
        let model = AppModel.shared
        guard model.part("act"), let client = model.client else { return }
        let plan = ActPlan.make(ask, apps: model.config?.actApps ?? [], shortcuts: ActLocal.shortcuts)
        if case .refuse(let why) = plan {
            await answer(client, ask.id, ok: false, error: why, failed: true)
            HUD.show("Spark wollte etwas, das der Begleiter nicht kann: \(why)", symbol: "hand.raised", seconds: 6)
            return
        }
        // "ohne Rückfrage" is chosen only on this Mac (Am PC handeln einstellen), never by the panel
        let auto = ActLocal.maySkip(ask.action)
        let front = NSWorkspace.shared.frontmostApplication
        if !auto {
            guard confirm(ask, plan: plan) else {
                await answer(client, ask.id, ok: false, error: "Nicht erlaubt.")
                return
            }
            if ActLocal.needsFront.contains(ask.action), let front,
               front.processIdentifier != ProcessInfo.processInfo.processIdentifier {
                front.activate(options: [])          // keys and window orders go to the window from before
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
        }
        let problem = run(plan)
        await answer(client, ask.id, ok: problem == nil, error: problem, auto: auto, failed: problem != nil)
        if let problem {
            HUD.show(problem, symbol: "exclamationmark.triangle")
        } else if auto {
            HUD.show("Spark (ohne Rückfrage): " + detail(plan), symbol: "hand.tap", seconds: 4)
        }
    }

    private func answer(_ client: SparkClient, _ id: String, ok: Bool, error: String?, auto: Bool = false,
                        failed: Bool = false) async {
        do {
            try await client.act(id: id, ok: ok, error: error, auto: auto, failed: failed)
        } catch {
            AppModel.shared.absorb(error)
        }
    }

    /// what the dialog says the Mac would do (from the checked plan, not only the Spark's text)
    private func detail(_ plan: ActPlan) -> String {
        switch plan {
        case .url(let u): return "Adresse öffnen: " + String(u.absoluteString.prefix(300))
        case .app(let a): return "Programm starten: " + a.name
        case .focus(let a): return "„\(a.name)“ nach vorn holen (oder starten)"
        case .media(let m):
            switch m {
            case "next": return "Medien: nächster Titel"
            case "previous": return "Medien: voriger Titel"
            default: return "Medien: Wiedergabe/Pause"
            }
        case .volume(let v):
            switch v {
            case "up": return "Lautstärke lauter"
            case "down": return "Lautstärke leiser"
            default: return "Ton aus/an"
            }
        case .lock: return "Bildschirm sperren"
        case .show: return "Einen Text anzeigen"
        case .window(let w):
            switch w {
            case "close": return "Fenster vorn schließen (⌘W)"
            case "minimize": return "Fenster vorn ins Dock (⌘M)"
            case "maximize": return "Fenster vorn zoomen"
            default: return "Vollbild an/aus (⌃⌘F)"
            }
        case .key(let k): return "Taste im Fenster vorn: " + (ActKeys.labels[k] ?? k)
        case .type(let t): return "Tippt ins Fenster vorn: „" + String(t.replacingOccurrences(of: "\n", with: " ").prefix(200)) + "“"
        case .folder(let f): return "Ordner öffnen: " + (ActFolders.labels[f] ?? f)
        case .power(let p): return p == "sleep" ? "Mac in den Ruhezustand" : "Bildschirm aus"
        case .shortcut(let n): return "Kurzbefehl ausführen: " + n
        case .refuse(let w): return w
        }
    }

    /// "Spark möchte: <text>. Erlauben?" — floating, in front, 60 s without answer = Nein. For a kind that may run
    /// without asking, the box "Künftig ohne Rückfrage" sets that on this Mac (only together with "Erlauben").
    private func confirm(_ ask: ActAsk, plan: ActPlan) -> Bool {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.alertStyle = .warning
        let text = DeskConfig.plain(ask.text, max: 300)
        a.messageText = "Spark möchte: \(text.isEmpty ? detail(plan) : text). Erlauben?"
        a.informativeText = detail(plan) + "\n\nOhne Antwort gilt nach 60 Sekunden „Nein“."
        a.addButton(withTitle: "Erlauben")
        let no = a.addButton(withTitle: "Nein")
        no.keyEquivalent = "\u{1b}"
        if ActLocal.autoOk.contains(ask.action) {
            a.showsSuppressionButton = true
            a.suppressionButton?.title = "Künftig ohne Rückfrage: " + (ActLocal.labels[ask.action] ?? ask.action)
            a.suppressionButton?.state = .off
        }
        a.window.level = .floating
        // a timer in the modal run loop mode; abortModal is the documented way to end a modal run from a timer
        let timer = Timer(timeInterval: Self.timeout, repeats: false) { _ in
            NSApp.abortModal()
        }
        RunLoop.main.add(timer, forMode: .modalPanel)
        let r = a.runModal()
        timer.invalidate()
        let allowed = r == .alertFirstButtonReturn
        if allowed, a.suppressionButton?.state == .on, !ActLocal.auto.contains(ask.action) {
            ActLocal.auto = ActLocal.auto + [ask.action]
            ActWait.shared.sendLocal()
        }
        return allowed
    }

    // ------------------------------------------------------------------ doing it

    /// nil when done, else a German reason
    private func run(_ plan: ActPlan) -> String? {
        switch plan {
        case .url(let u):
            return NSWorkspace.shared.open(u) ? nil : "Die Adresse ließ sich nicht öffnen."
        case .app(let a):
            return openApp(a)
        case .focus(let a):
            return focusApp(a)
        case .media(let m):
            guard Access.trusted else { return needAccess() }
            switch m {
            case "next": MediaKeys.press(MediaKeys.next)
            case "previous": MediaKeys.press(MediaKeys.previous)
            default: MediaKeys.press(MediaKeys.play)     // play and pause: the same toggle key
            }
            return nil
        case .volume(let v):
            guard Access.trusted else { return needAccess() }
            switch v {
            case "up": MediaKeys.press(MediaKeys.soundUp)
            case "down": MediaKeys.press(MediaKeys.soundDown)
            default: MediaKeys.press(MediaKeys.mute)
            }
            return nil
        case .lock:
            return ScreenLock.lock() ? nil : "Der Bildschirm ließ sich nicht sperren."
        case .show(let t):
            ShowText.show(t)
            return nil
        case .window(let w):
            guard Access.trusted else { return needAccess() }
            return ActMac.window(w)
        case .key(let k):
            guard Access.trusted else { return needAccess() }
            return ActMac.key(k)
        case .type(let t):
            guard Access.trusted else { return needAccess() }
            ActMac.type(t)
            return nil
        case .folder(let f):
            return ActMac.folder(f)
        case .power(let p):
            return ActMac.power(p)
        case .shortcut(let n):
            return ActMac.shortcut(n)
        case .refuse(let w):
            return w
        }
    }

    private func focusApp(_ a: ActApp) -> String? {
        let own = ProcessInfo.processInfo.processIdentifier
        let running = NSWorkspace.shared.runningApplications.first { r in
            guard r.processIdentifier != own else { return false }
            switch a.target {
            case .bundle(let b)?: return r.bundleIdentifier?.lowercased() == b.lowercased()
            case .path(let p)?: return r.bundleURL?.standardizedFileURL.path == URL(fileURLWithPath: p).standardizedFileURL.path
            case .name(let n)?: return r.bundleURL?.deletingPathExtension().lastPathComponent.lowercased() == n.lowercased()
            case nil: return false
            }
        }
        if let running {
            if running.isHidden { running.unhide() }
            running.activate(options: [])
            return nil
        }
        return openApp(a)
    }

    private func needAccess() -> String {
        Access.askOnce()
        return "Für Tasten, Fenster und Tippen braucht der Begleiter die Freigabe Bedienungshilfen."
    }

    private func openApp(_ a: ActApp) -> String? {
        let fm = FileManager.default
        var url: URL?
        switch a.target {
        case .path(let p)?:
            if fm.fileExists(atPath: p) { url = URL(fileURLWithPath: p, isDirectory: true) }
        case .bundle(let b)?:
            url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: b)
        case .name(let n)?:
            let dirs = ["/Applications", "/System/Applications", "/System/Applications/Utilities",
                        "/Applications/Utilities", NSHomeDirectory() + "/Applications"]
            url = dirs.map { URL(fileURLWithPath: $0 + "/" + n + ".app", isDirectory: true) }
                .first { fm.fileExists(atPath: $0.path) }
        case nil:
            url = nil
        }
        guard let url else { return "„\(a.name)“ ist auf diesem Mac nicht zu finden." }
        let cfg = NSWorkspace.OpenConfiguration()
        cfg.activates = true
        NSWorkspace.shared.openApplication(at: url, configuration: cfg) { _, _ in }
        return nil
    }
}

/// The media and volume keys of the keyboard (NX_KEYTYPE_*), as system-defined events (needs Accessibility).
enum MediaKeys {
    static let soundUp: Int32 = 0       // NX_KEYTYPE_SOUND_UP
    static let soundDown: Int32 = 1     // NX_KEYTYPE_SOUND_DOWN
    static let mute: Int32 = 7          // NX_KEYTYPE_MUTE
    static let play: Int32 = 16         // NX_KEYTYPE_PLAY
    static let next: Int32 = 17         // NX_KEYTYPE_NEXT
    static let previous: Int32 = 18     // NX_KEYTYPE_PREVIOUS

    static func press(_ key: Int32) {
        for down in [true, false] {
            let flags = NSEvent.ModifierFlags(rawValue: down ? 0xa00 : 0xb00)
            let data1 = Int((key << 16) | ((down ? 0xa : 0xb) << 8))
            guard let e = NSEvent.otherEvent(with: .systemDefined, location: .zero, modifierFlags: flags,
                                             timestamp: 0, windowNumber: 0, context: nil, subtype: 8,
                                             data1: data1, data2: -1) else { continue }
            e.cgEvent?.post(tap: .cghidEventTap)
        }
    }
}

/// Locks the screen: SACLockScreenImmediate (what the menu "Bildschirm sperren" uses) when it is there, else
/// `pmset displaysleepnow` (locks when "Passwort sofort verlangen" is set, as by default).
enum ScreenLock {
    private typealias LockFn = @convention(c) () -> Int32

    static func lock() -> Bool {
        let path = "/System/Library/PrivateFrameworks/login.framework/Versions/Current/login"
        if let h = dlopen(path, RTLD_LAZY) {
            defer { dlclose(h) }
            if let sym = dlsym(h, "SACLockScreenImmediate") {
                let f = unsafeBitCast(sym, to: LockFn.self)
                _ = f()
                return true
            }
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
        p.arguments = ["displaysleepnow"]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
        } catch {
            return false
        }
        p.waitUntilExit()
        return p.terminationStatus == 0
    }
}

/// "show": the Spark's text in a plain window (selectable, never markup).
@MainActor
enum ShowText {
    static func show(_ text: String) {
        let t = String(text.prefix(5000))
        Windows.shared.close("act-show")
        Windows.shared.show("act-show", title: "Vom Spark", size: NSSize(width: 460, height: 300), floating: true) {
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        if FacePref.on { FaceView(size: 28) }
                        Text(verbatim: "Vom Spark")
                            .font(.system(size: 14, weight: .semibold))
                        Spacer()
                    }
                    ScrollView {
                        Text(verbatim: t)
                            .font(.system(size: 13))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    HStack {
                        Spacer()
                        Button("Kopieren") { Clip.put(t) }
                            .buttonStyle(SoftButtonStyle())
                        Button("Schließen") { Windows.shared.close("act-show") }
                            .buttonStyle(PrimaryButtonStyle())
                            .keyboardShortcut(.cancelAction)
                    }
                }
                .padding(14)
            }
            .background(Theme.card)
            .foregroundColor(Theme.fg)
            .frame(minWidth: 360, minHeight: 220)
        }
    }
}
