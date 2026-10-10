import AppKit
import SwiftUI

/// Small borderless panels at the top of the screen that never take the focus from the person's program.
@MainActor
enum FloatingPanel {
    static func make() -> NSPanel {
        let p = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 300, height: 60),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
        p.level = .statusBar
        p.isFloatingPanel = true
        p.hidesOnDeactivate = false
        p.backgroundColor = .clear
        p.isOpaque = false
        p.hasShadow = true
        p.isReleasedWhenClosed = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        return p
    }

    static func show<V: View>(_ panel: NSPanel, _ view: V) {
        let host = NSHostingView(rootView: view)
        let size = host.fittingSize
        host.frame = NSRect(origin: .zero, size: size)
        panel.contentView = host
        panel.setContentSize(size)
        let screen = NSScreen.main ?? NSScreen.screens.first
        if let s = screen?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: s.midX - size.width / 2, y: s.maxY - size.height - 10))
        }
        panel.orderFrontRegardless()
    }
}

struct BubbleView: View {
    let text: String
    let symbol: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: symbol)
                .foregroundColor(.accentColor)
            Text(verbatim: text)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(6)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(width: 380, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(nsColor: .windowBackgroundColor)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.3)))
    }
}

/// A short message that disappears by itself.
@MainActor
enum HUD {
    private static var panel: NSPanel?
    private static var hideTask: Task<Void, Never>?

    static func show(_ text: String, symbol: String = "sparkles", seconds: Double = 4) {
        hideTask?.cancel()
        let p = panel ?? FloatingPanel.make()
        panel = p
        FloatingPanel.show(p, BubbleView(text: text, symbol: symbol))
        hideTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            if !Task.isCancelled { panel?.orderOut(nil) }
        }
    }

    static func hide() {
        hideTask?.cancel()
        panel?.orderOut(nil)
    }
}

/// Always visible while the microphone records.
struct RecordingView: View {
    @ObservedObject var dictation: Dictation
    let hotkey: String

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(Color.red)
                .frame(width: 12, height: 12)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: "Aufnahme läuft · \(dictation.elapsed / 60):\(String(format: "%02d", dictation.elapsed % 60)) / 1:00")
                    .font(.system(size: 13, weight: .semibold))
                Text(verbatim: hotkey.isEmpty ? "Noch einmal das Kürzel zum Beenden" : "\(hotkey) beendet die Aufnahme")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer(minLength: 8)
            Button("Fertig") { dictation.finish() }
            Button("Verwerfen") { dictation.discard() }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(width: 420)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(nsColor: .windowBackgroundColor)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.red.opacity(0.6), lineWidth: 1.5))
    }
}

@MainActor
enum RecordingIndicator {
    private static var panel: NSPanel?

    static func show(_ dictation: Dictation, hotkey: String) {
        HUD.hide()
        let p = panel ?? FloatingPanel.make()
        panel = p
        FloatingPanel.show(p, RecordingView(dictation: dictation, hotkey: hotkey))
    }

    static func hide() {
        panel?.orderOut(nil)
    }
}

/// The program's normal windows (pairing, settings, writing help, questions).
@MainActor
final class Windows: NSObject, NSWindowDelegate {
    static let shared = Windows()

    private var open: [String: NSWindow] = [:]
    private var onClose: [String: () -> Void] = [:]

    func isOpen(_ id: String) -> Bool { open[id] != nil }

    func window(_ id: String) -> NSWindow? { open[id] }

    @discardableResult
    func show<V: View>(_ id: String, title: String, size: NSSize, floating: Bool = false,
                       @ViewBuilder content: () -> V) -> NSWindow {
        if let w = open[id] {
            NSApp.activate(ignoringOtherApps: true)
            w.makeKeyAndOrderFront(nil)
            return w
        }
        let w = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable],
                         backing: .buffered, defer: false)
        w.title = title
        w.isReleasedWhenClosed = false
        w.identifier = NSUserInterfaceItemIdentifier(id)
        w.contentViewController = NSHostingController(rootView: content())
        w.setContentSize(size)
        w.center()
        w.delegate = self
        if floating { w.level = .floating }
        open[id] = w
        NSApp.activate(ignoringOtherApps: true)
        w.makeKeyAndOrderFront(nil)
        return w
    }

    /// Ends a modal run (also from a Task, where stopModal alone waits for the next event).
    static func stopModal() {
        guard NSApp.modalWindow != nil else { return }
        NSApp.stopModal()
        if let e = NSEvent.otherEvent(with: .applicationDefined, location: .zero, modifierFlags: [], timestamp: 0,
                                      windowNumber: 0, context: nil, subtype: 0, data1: 0, data2: 0) {
            NSApp.postEvent(e, atStart: true)
        }
    }

    /// Runs once when the window `id` closes (by its close button or by close(_:)).
    func whenClosed(_ id: String, _ f: @escaping () -> Void) {
        onClose[id] = f
    }

    func close(_ id: String) {
        open[id]?.close()
    }

    func windowWillClose(_ notification: Notification) {
        guard let w = notification.object as? NSWindow, let id = w.identifier?.rawValue else { return }
        open[id] = nil
        let done = onClose.removeValue(forKey: id)
        done?()
    }
}
