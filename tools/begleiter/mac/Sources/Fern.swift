import AppKit
import ApplicationServices
import Carbon
import SwiftUI

// Rechner fernsteuern (Dominik 2026-10-17), Stufe 1: the fixed orders behind "focus", "window", "key", "type",
// "folder", "power" and "shortcut", waiting for the Spark's wishes (GET /api/desk/wait) and the window
// "Am PC handeln einstellen". Only while the part "act" is on.

/// The new orders on this Mac. Every key comes from a fixed list; there is no free key combination.
@MainActor
enum ActMac {
    private static let keys: [String: (code: Int, flags: CGEventFlags)] = [
        "next": (kVK_PageDown, []), "previous": (kVK_PageUp, []), "space": (kVK_Space, []),
        "enter": (kVK_Return, []), "escape": (kVK_Escape, []), "tab": (kVK_Tab, []),
        "undo": (kVK_ANSI_Z, .maskCommand), "redo": (kVK_ANSI_Z, [.maskCommand, .maskShift]),
        "copy": (kVK_ANSI_C, .maskCommand), "paste": (kVK_ANSI_V, .maskCommand), "save": (kVK_ANSI_S, .maskCommand),
        "reload": (kVK_ANSI_R, .maskCommand), "find": (kVK_ANSI_F, .maskCommand),
    ]

    static func key(_ name: String) -> String? {
        guard let k = keys[name] else { return "Diese Taste ist nicht erlaubt." }
        Keys.press(k.code, flags: k.flags)
        return nil
    }

    /// the front window; nil when nothing or the Begleiter itself is in front
    private static func frontApp() -> NSRunningApplication? {
        guard let app = NSWorkspace.shared.frontmostApplication,
              app.processIdentifier != ProcessInfo.processInfo.processIdentifier else { return nil }
        return app
    }

    static func window(_ what: String) -> String? {
        guard let app = frontApp() else { return "Vorn liegt kein Programmfenster." }
        switch what {
        case "close": Keys.press(kVK_ANSI_W, flags: .maskCommand)
        case "minimize": Keys.press(kVK_ANSI_M, flags: .maskCommand)
        case "fullscreen": Keys.press(kVK_ANSI_F, flags: [.maskCommand, .maskControl])
        case "maximize":
            // the green button's "zoom" of the front window (Accessibility)
            let ax = AXUIElementCreateApplication(app.processIdentifier)
            var win: CFTypeRef?
            guard AXUIElementCopyAttributeValue(ax, kAXFocusedWindowAttribute as CFString, &win) == .success,
                  let win, CFGetTypeID(win) == AXUIElementGetTypeID() else { return "Kein Fenster vorn gefunden." }
            var button: CFTypeRef?
            guard AXUIElementCopyAttributeValue(win as! AXUIElement, kAXZoomButtonAttribute as CFString, &button) == .success,
                  let button, CFGetTypeID(button) == AXUIElementGetTypeID(),
                  AXUIElementPerformAction(button as! AXUIElement, kAXPressAction as CFString) == .success else {
                return "Das Fenster lässt sich nicht zoomen."
            }
        default: return "Unbekannte Fenster-Aktion."
        }
        return nil
    }

    /// types the text into the front window (Unicode, a line break is Return)
    static func type(_ text: String) {
        let src = CGEventSource(stateID: .hidSystemState)
        for (i, line) in text.components(separatedBy: "\n").enumerated() {
            if i > 0 { Keys.press(kVK_Return, flags: []) }
            var chunk: [UniChar] = []
            func flush() {
                guard !chunk.isEmpty,
                      let down = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true),
                      let up = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: false) else { return }
                down.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: chunk)
                up.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: chunk)
                down.post(tap: .cghidEventTap)
                up.post(tap: .cghidEventTap)
                chunk = []
            }
            for u in line.utf16 where u >= 32 {
                chunk.append(u)
                if chunk.count >= 16 { flush() }
            }
            flush()
        }
    }

    static func folder(_ which: String) -> String? {
        let fm = FileManager.default
        let url: URL?
        switch which {
        case "documents": url = fm.urls(for: .documentDirectory, in: .userDomainMask).first
        case "downloads": url = fm.urls(for: .downloadsDirectory, in: .userDomainMask).first
        case "desktop": url = fm.urls(for: .desktopDirectory, in: .userDomainMask).first
        case "pictures": url = fm.urls(for: .picturesDirectory, in: .userDomainMask).first
        case "music": url = fm.urls(for: .musicDirectory, in: .userDomainMask).first
        case "videos": url = fm.urls(for: .moviesDirectory, in: .userDomainMask).first
        case "recent":
            url = URL(fileURLWithPath: "/System/Library/CoreServices/Finder.app/Contents/Resources/MyLibraries/myDocuments.cannedSearch")
        default: url = nil
        }
        guard let url, fm.fileExists(atPath: url.path) else { return "Diesen Ordner gibt es auf dem Mac nicht." }
        return NSWorkspace.shared.open(url) ? nil : "Der Ordner ließ sich nicht öffnen."
    }

    static func power(_ what: String) -> String? {
        let ok = run("/usr/bin/pmset", [what == "sleep" ? "sleepnow" : "displaysleepnow"], wait: true)
        return ok ? nil : (what == "sleep" ? "Der Mac ließ sich nicht schlafen legen." : "Der Bildschirm ging nicht aus.")
    }

    /// runs a Shortcut released on this Mac (the name only; `shortcuts run` gets it as one argument)
    static func shortcut(_ name: String) -> String? {
        guard ActLocal.shortcuts.contains(name) else { return "Diesen Kurzbefehl gibt es hier nicht." }
        return run("/usr/bin/shortcuts", ["run", name], wait: false) ? nil : "Der Kurzbefehl ließ sich nicht starten."
    }

    /// the names of this Mac's Shortcuts (`shortcuts list`), for the settings window
    nonisolated static func shortcutNames() -> [String] {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/shortcuts")
        p.arguments = ["list"]
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        p.standardInput = FileHandle.nullDevice
        do { try p.run() } catch { return [] }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        let text = String(decoding: data.prefix(256 * 1024), as: UTF8.self)
        return Array(text.split(separator: "\n").map(String.init).filter(ActLocal.validName).prefix(300))
    }

    private static func run(_ tool: String, _ args: [String], wait: Bool) -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool)
        p.arguments = args
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return false }
        guard wait else { return true }
        p.waitUntilExit()
        return p.terminationStatus == 0
    }
}

/// Waits for the Spark's wishes (GET /api/desk/wait, held up to 25 s) so they arrive at once, and tells the Spark
/// what the person chose here (shortcut names, kinds without the dialog).
@MainActor
final class ActWait {
    static let shared = ActWait()
    private var task: Task<Void, Never>?
    private var sent: String?

    func apply(on: Bool) {
        if on {
            if task == nil {
                task = Task { @MainActor in await self.loop() }
            }
            sendLocal()
        } else {
            task?.cancel()
            task = nil
            sent = nil
            Windows.shared.close("act-settings")
        }
    }

    private func loop() async {
        while !Task.isCancelled {
            let model = AppModel.shared
            guard model.part("act") || model.part("view"), model.config?.actWait == true, let client = model.client else {
                try? await Task.sleep(nanoseconds: 15_000_000_000)
                continue
            }
            do {
                let d = try await client.get("api/desk/wait", timeout: 60)
                if !Task.isCancelled, model.part("act") {
                    ActCenter.shared.take(ActAsk.list(d["asks"]))
                }
                // Stufe 2: a request to show the screen comes with the same wait (part "view")
                if !Task.isCancelled, model.part("view") {
                    ViewCenter.shared.take(ViewAsk.list(d["views"]))
                }
            } catch is CancellationError {
                return
            } catch {
                // the poll reports a missing Spark or a Notaus; here only try again a little later
                try? await Task.sleep(nanoseconds: 15_000_000_000)
            }
        }
    }

    /// POST /api/desk/local, only when something changed
    func sendLocal() {
        let model = AppModel.shared
        guard model.part("act"), let client = model.client else { return }
        let names = ActLocal.shortcuts
        let auto = ActLocal.auto
        let state = names.joined(separator: "|") + "#" + auto.joined(separator: "|")
        guard state != sent else { return }
        Task { @MainActor in
            do {
                _ = try await client.postJSON("api/desk/local", ["shortcuts": names, "auto": auto], timeout: 20)
                self.sent = state
            } catch {
                model.absorb(error)
            }
        }
    }
}

/// "Am PC handeln einstellen": which kinds run without the dialog, which Shortcuts the Spark may name. Only here,
/// never in the panel (it only shows the result).
@MainActor
final class ActSettingsModel: ObservableObject {
    @Published var auto: Set<String> = Set(ActLocal.auto)
    @Published var shortcuts: Set<String> = Set(ActLocal.shortcuts)
    @Published var available: [String] = []
    @Published var loading = true

    func load() {
        Task.detached {
            let names = ActMac.shortcutNames()
            await MainActor.run {
                self.available = names
                self.loading = false
            }
        }
    }

    func setAuto(_ kind: String, _ on: Bool) {
        if on { auto.insert(kind) } else { auto.remove(kind) }
        ActLocal.auto = ActLocal.autoOk.filter { auto.contains($0) }
        ActWait.shared.sendLocal()
    }

    func setShortcut(_ name: String, _ on: Bool) {
        if on { shortcuts.insert(name) } else { shortcuts.remove(name) }
        ActLocal.shortcuts = shortcuts.sorted()
        ActWait.shared.sendLocal()
    }
}

struct ActSettingsView: View {
    @ObservedObject var m: ActSettingsModel

    private static let symbols: [String: String] = [
        "app": "app", "media": "music.note", "volume": "speaker.wave.2", "lock": "lock", "focus": "macwindow",
        "window": "macwindow.on.rectangle", "key": "keyboard", "folder": "folder", "power": "moon",
        "shortcut": "square.stack.3d.up",
    ]

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    SectionLabel(text: "Ohne Rückfrage")
                    PanelBox {
                        ForEach(Array(ActLocal.autoOk.enumerated()), id: \.element) { i, k in
                            if i > 0 { RowLine() }
                            SwitchRow(title: ActLocal.labels[k] ?? k, symbol: Self.symbols[k] ?? "circle",
                                      isOn: Binding(get: { m.auto.contains(k) }, set: { m.setAuto(k, $0) }))
                        }
                    }
                    note("Eingeschaltete Arten führt der Begleiter sofort aus und zeigt danach einen Hinweis. Seiten öffnen, Text tippen und Text zeigen fragen immer.")
                    SectionLabel(text: "Kurzbefehle")
                        .padding(.top, 12)
                    if m.loading {
                        note("Lade die Kurzbefehle …")
                    } else if m.available.isEmpty {
                        note("Keine Kurzbefehle gefunden (oder ihre Namen enthalten Zeichen wie / oder \").")
                    } else {
                        PanelBox {
                            ForEach(Array(m.available.enumerated()), id: \.element) { i, n in
                                if i > 0 { RowLine() }
                                SwitchRow(title: n, symbol: "square.stack.3d.up",
                                          isOn: Binding(get: { m.shortcuts.contains(n) }, set: { m.setShortcut(n, $0) }))
                            }
                        }
                    }
                    note("Aus der App Kurzbefehle. Der Spark darf eingeschaltete auf Zuruf starten („Führ am Mac den Kurzbefehl Feierabend aus“) und kennt nur den Namen.")
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.bg)
            VStack(spacing: 0) {
                Rectangle().fill(Theme.line).frame(height: 1)
                HStack {
                    Spacer()
                    Button("Fertig") { Windows.shared.close("act-settings") }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.defaultAction)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
            }
            .background(Theme.soft)
        }
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 420, minHeight: 420)
    }

    private func note(_ text: String) -> some View {
        Text(verbatim: text)
            .font(.system(size: 11.5))
            .foregroundColor(Theme.muted)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 2)
    }
}

enum ActSettings {
    @MainActor
    static func show() {
        let m = ActSettingsModel()
        m.load()
        Windows.shared.show("act-settings", title: "Spark-Begleiter – Am PC handeln einstellen",
                            size: NSSize(width: 460, height: 640)) {
            ActSettingsView(m: m)
        }
    }
}
