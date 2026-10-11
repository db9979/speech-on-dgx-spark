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
        HStack(alignment: .top, spacing: 10) {
            FaceView(size: 22)
            Image(systemName: symbol)
                .foregroundColor(Theme.accent)
                .padding(.top, 2)
            Text(verbatim: text)
                .foregroundColor(Theme.fg)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(6)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(width: 380, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1))
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

/// Always visible while the microphone records (design A): a dark pill with a red dot, "Ich höre zu", little
/// level bars, the time and the hotkey that ends it.
struct RecordingView: View {
    @ObservedObject var dictation: Dictation
    let hotkey: String

    private static let shape: [Double] = [0.4, 0.8, 0.55, 0.95, 0.35]

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(Theme.bad)
                .frame(width: 9, height: 9)
            Text(verbatim: "Ich höre zu")
                .font(.system(size: 13, weight: .semibold))
            HStack(spacing: 3) {
                ForEach(0..<Self.shape.count, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(Theme.accent2)
                        .frame(width: 3, height: barHeight(i))
                }
            }
            .frame(height: 18)
            .animation(.easeOut(duration: 0.12), value: dictation.level)
            .accessibilityHidden(true)
            Text(verbatim: "\(dictation.elapsed / 60):\(String(format: "%02d", dictation.elapsed % 60)) / 1:00")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(Theme.pillFg.opacity(0.7))
            if !hotkey.isEmpty {
                KeyChip(text: hotkey, dark: true)
                    .help(Text(verbatim: "\(hotkey) beendet die Aufnahme"))
            }
            Button("Fertig") { dictation.finish() }
                .buttonStyle(PillButtonStyle(primary: true))
            Button("Verwerfen") { dictation.discard() }
                .buttonStyle(PillButtonStyle(primary: false))
        }
        .foregroundColor(Theme.pillFg)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Capsule().fill(Theme.visor))
        .overlay(Capsule().stroke(Color.white.opacity(0.08), lineWidth: 1))
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(verbatim: "Aufnahme läuft"))
    }

    private func barHeight(_ i: Int) -> CGFloat {
        let l = min(max(dictation.level, 0.12), 1)
        return CGFloat(4 + 14 * Self.shape[i] * l)
    }
}

/// Small buttons on the dark recording pill.
struct PillButtonStyle: ButtonStyle {
    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: primary ? .semibold : .regular))
            .foregroundColor(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Capsule().fill(primary ? AnyShapeStyle(Theme.diagonal) : AnyShapeStyle(Color.white.opacity(0.12))))
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(Capsule())
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
        w.titlebarAppearsTransparent = true
        w.backgroundColor = Theme.nsCard
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
