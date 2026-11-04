import AppKit
import ApplicationServices
import Carbon
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// The one core for showing and operating this Mac's screen (Spontanhilfe S2c, plan spontanhilfe/s2-plan.md): the
// Begleiter's Fernsicht (Fernsicht.swift) and the program SparkHilfe (tools/sparkhilfe/mac) both take the picture,
// the fixed lists of inputs, the key presses, the red frame with the bar and the question with its 60 seconds only
// from here (tools/sparkhilfe/mac/build.sh compiles this file into SparkHilfe; the colours come from Theme.swift).
// No ⌘-Tab, no ⌘-Space, no ⌃⌥⌫, no free key combination.

/// The keys a viewer may press (fernsicht.KEYS in the panel) and the mouse buttons (fernsicht.BUTTONS).
enum ViewKeys {
    static let keys: [String: (code: Int, flags: CGEventFlags)] = [
        "enter": (kVK_Return, []), "escape": (kVK_Escape, []), "tab": (kVK_Tab, []), "backspace": (kVK_Delete, []),
        "delete": (kVK_ForwardDelete, []), "space": (kVK_Space, []), "up": (kVK_UpArrow, []), "down": (kVK_DownArrow, []),
        "left": (kVK_LeftArrow, []), "right": (kVK_RightArrow, []), "home": (kVK_Home, []), "end": (kVK_End, []),
        "pageup": (kVK_PageUp, []), "pagedown": (kVK_PageDown, []),
        "undo": (kVK_ANSI_Z, .maskCommand), "redo": (kVK_ANSI_Z, [.maskCommand, .maskShift]),
        "copy": (kVK_ANSI_C, .maskCommand), "paste": (kVK_ANSI_V, .maskCommand), "save": (kVK_ANSI_S, .maskCommand),
        "reload": (kVK_ANSI_R, .maskCommand), "find": (kVK_ANSI_F, .maskCommand),
    ]
    static let buttons: Set<String> = ["left", "right", "double"]
    /// typed text at most this long (fernsicht.TEXT_MAX)
    static let textMax = 200
    /// pictures at most four a second (spontansteuern.FPS)
    static let frameGap: UInt64 = 250_000_000
}

/// Key presses and typing for the person (needs Accessibility).
enum Keys {
    static func press(_ code: Int, flags: CGEventFlags = .maskCommand) {
        let src = CGEventSource(stateID: .hidSystemState)
        guard let down = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(code), keyDown: true),
              let up = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(code), keyDown: false) else { return }
        down.flags = flags
        up.flags = flags
        down.post(tap: .cghidEventTap)
        up.post(tap: .cghidEventTap)
    }

    /// Waits (at most a second) until ⌥, ⌃ and ⇧ of the hotkey are let go, so they do not mix into ⌘C/⌘V.
    static func waitForModifiers() async {
        for _ in 0..<20 {
            let f = CGEventSource.flagsState(.combinedSessionState)
            if !f.contains(.maskAlternate) && !f.contains(.maskControl) && !f.contains(.maskShift) { return }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
    }

    /// types the text into the front window (Unicode, a line break is Return)
    static func type(_ text: String) {
        let src = CGEventSource(stateID: .hidSystemState)
        for (i, line) in text.components(separatedBy: "\n").enumerated() {
            if i > 0 { press(kVK_Return, flags: []) }
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
}

/// One picture of the main display as JPEG, at most `side` pixels on the longer side (only in memory:
/// screencapture's file lives in a private folder and is deleted at once).
enum ViewShot {
    static func take(side: Int = 1600, quality: Double = 0.6) -> (data: Data, width: Int, height: Int)? {
        let fm = FileManager.default
        let dir = fm.temporaryDirectory.appendingPathComponent("spark-schirm-" + UUID().uuidString, isDirectory: true)
        guard (try? fm.createDirectory(at: dir, withIntermediateDirectories: false,
                                       attributes: [.posixPermissions: 0o700])) != nil else { return nil }
        defer { try? fm.removeItem(at: dir) }
        let file = dir.appendingPathComponent("schirm.jpg")
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        p.arguments = ["-x", "-m", "-t", "jpg", file.path]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
        } catch {
            return nil
        }
        p.waitUntilExit()
        guard p.terminationStatus == 0, let src = CGImageSourceCreateWithURL(file as CFURL, nil) else { return nil }
        let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                     kCGImageSourceThumbnailMaxPixelSize: side,
                                     kCGImageSourceCreateThumbnailWithTransform: true]
        guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { return nil }
        let out = NSMutableData()
        guard let dst = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(dst, img, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(dst) else { return nil }
        return (out as Data, img.width, img.height)
    }
}

/// The inputs: a point 0..1 of the picture on the main display, clicks, scrolling, keys from the list, text.
enum ViewInput {
    static func point(_ e: [String: Any], display: CGDirectDisplayID) -> CGPoint? {
        guard let x = (e["x"] as? NSNumber)?.doubleValue, let y = (e["y"] as? NSNumber)?.doubleValue,
              (0...1).contains(x), (0...1).contains(y) else { return nil }
        let b = CGDisplayBounds(display)
        return CGPoint(x: b.minX + x * (b.width - 1), y: b.minY + y * (b.height - 1))
    }

    /// one input; anything unknown, outside the picture or without Accessibility is skipped
    static func apply(_ e: [String: Any], display: CGDirectDisplayID) {
        guard AXIsProcessTrusted() else { return }
        switch e["t"] as? String {
        case "move":
            if let p = point(e, display: display) { post(.mouseMoved, p, .left) }
        case "click":
            let b = e["b"] as? String ?? "left"
            if ViewKeys.buttons.contains(b), let p = point(e, display: display) { click(p, b) }
        case "scroll":
            if let dy = (e["dy"] as? NSNumber)?.intValue, (-10...10).contains(dy), dy != 0 {
                CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 1, wheel1: Int32(dy), wheel2: 0, wheel3: 0)?
                    .post(tap: .cghidEventTap)
            }
        case "key":
            if let k = ViewKeys.keys[e["k"] as? String ?? ""] { Keys.press(k.code, flags: k.flags) }
        case "text":
            if let s = e["s"] as? String, (1...ViewKeys.textMax).contains(s.count) { Keys.type(s) }
        default:
            break
        }
    }

    private static func post(_ type: CGEventType, _ p: CGPoint, _ button: CGMouseButton, clicks: Int64 = 1) {
        guard let ev = CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: p, mouseButton: button) else { return }
        ev.setIntegerValueField(.mouseEventClickState, value: clicks)
        ev.post(tap: .cghidEventTap)
    }

    private static func click(_ p: CGPoint, _ button: String) {
        if button == "right" {
            post(.rightMouseDown, p, .right)
            post(.rightMouseUp, p, .right)
            return
        }
        post(.mouseMoved, p, .left)
        post(.leftMouseDown, p, .left)
        post(.leftMouseUp, p, .left)
        if button == "double" {
            post(.leftMouseDown, p, .left, clicks: 2)
            post(.leftMouseUp, p, .left, clicks: 2)
        }
    }
}

/// The red frame around the main display (clicks go through) and the bar with „Beenden“ on top; both stay out of
/// the pictures.
@MainActor
final class ViewMarks: NSObject {
    private var windows: [NSWindow] = []
    private let label = NSTextField(labelWithString: "")
    private let onEnd: @MainActor () -> Void
    private var bar: NSPanel?
    private var frame = NSRect.zero

    init(display: CGDirectDisplayID, text: String, end: String, onEnd: @escaping @MainActor () -> Void) {
        self.onEnd = onEnd
        super.init()
        let key = NSDeviceDescriptionKey("NSScreenNumber")
        guard let screen = NSScreen.screens.first(where: { ($0.deviceDescription[key] as? NSNumber)?.uint32Value == display })
                ?? NSScreen.main else { return }
        frame = screen.frame
        let border = NSWindow(contentRect: frame, styleMask: .borderless, backing: .buffered, defer: false)
        border.isReleasedWhenClosed = false
        border.isOpaque = false
        border.backgroundColor = .clear
        border.ignoresMouseEvents = true
        border.level = .screenSaver
        border.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        border.sharingType = .none            // our own windows stay out of the pictures
        let edge = NSView(frame: NSRect(origin: .zero, size: frame.size))
        edge.wantsLayer = true
        edge.layer?.borderColor = Theme.nsBad.cgColor
        edge.layer?.borderWidth = 4
        border.contentView = edge
        border.orderFrontRegardless()
        windows.append(border)

        let bar = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 420, height: 40),
                          styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        bar.isReleasedWhenClosed = false
        bar.level = .screenSaver
        bar.isFloatingPanel = true
        bar.hidesOnDeactivate = false
        bar.collectionBehavior = [.canJoinAllSpaces, .stationary]
        bar.sharingType = .none
        bar.backgroundColor = Theme.nsBad
        label.stringValue = text
        label.textColor = Theme.nsOnAccent
        label.font = .boldSystemFont(ofSize: 13)
        let button = NSButton(title: end, target: self, action: #selector(endClicked))
        button.bezelStyle = .rounded
        let stack = NSStackView(views: [label, button])
        stack.orientation = .horizontal
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 8, left: 14, bottom: 8, right: 10)
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = NSView()
        bar.contentView = content
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])
        self.bar = bar
        place()
        bar.orderFrontRegardless()
        windows.append(bar)
    }

    /// a new text in the bar (it grows or shrinks with it)
    func say(_ text: String) {
        label.stringValue = text
        place()
    }

    func close() {
        windows.forEach { $0.orderOut(nil) }
        windows = []
        bar = nil
    }

    private func place() {
        guard let bar, let content = bar.contentView, let stack = content.subviews.first else { return }
        let size = stack.fittingSize
        bar.setFrame(NSRect(x: frame.midX - size.width / 2, y: frame.maxY - size.height - 40,
                            width: size.width, height: size.height), display: true)
    }

    @objc private func endClicked() {
        onEnd()
    }
}

/// The question at this Mac: the first button (Ablehnen, Stopp) is the default, so Return alone allows nothing; without
/// an answer the first button counts after `timeout` seconds. Returns the index of the button.
@MainActor
enum ViewAlert {
    static func ask(message: String, info: String, buttons: [String], timeout: TimeInterval,
                    countdown: String? = nil, hidden: Bool = false, level: NSWindow.Level = .floating) -> Int {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.alertStyle = .warning
        a.messageText = message
        a.informativeText = info
        for b in buttons { a.addButton(withTitle: b) }
        let clock = AlertClock(left: Int(timeout), countdown: countdown)
        if countdown != nil { a.accessoryView = clock.label }
        a.window.level = level
        if hidden { a.window.sharingType = .none }
        let timer = Timer(timeInterval: 1, target: clock, selector: #selector(AlertClock.tick(_:)), userInfo: nil, repeats: true)
        RunLoop.main.add(timer, forMode: .modalPanel)
        let r = a.runModal()
        timer.invalidate()
        let i = r.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
        return (0..<buttons.count).contains(i) ? i : 0
    }
}

/// the seconds left under the question; at 0 the question ends as if the first button was pressed
@MainActor
private final class AlertClock: NSObject {
    let label = NSTextField(labelWithString: "")
    private var left: Int
    private let countdown: String?

    init(left: Int, countdown: String?) {
        self.left = left
        self.countdown = countdown
        super.init()
        label.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        label.frame = NSRect(x: 0, y: 0, width: 320, height: 18)
        show()
    }

    @objc func tick(_ t: Timer) {
        left -= 1
        show()
        if left <= 0 {
            t.invalidate()
            NSApp.abortModal()
        }
    }

    private func show() {
        if let countdown { label.stringValue = countdown.replacingOccurrences(of: "{0}", with: String(max(left, 0))) }
    }
}
