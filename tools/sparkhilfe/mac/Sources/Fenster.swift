import AppKit

/// Das kleine Fenster mit dem Stand („Verbinde …“, die zwei Freigaben, „bitte neu laden“, „beendet“) und „Schließen“.
/// Schließen beendet das Programm.
@MainActor
final class StatusFenster: NSObject, NSWindowDelegate {
    private let window: NSWindow
    private let title = NSTextField(labelWithString: Texte.t("fenster"))
    private let text = NSTextField(wrappingLabelWithString: "")
    private let buttons = NSStackView()
    private let onClose: @MainActor () -> Void
    private var actions: [@MainActor () -> Void] = []

    init(onClose: @escaping @MainActor () -> Void) {
        self.onClose = onClose
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 160),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        super.init()
        window.title = Texte.t("fenster")
        window.isReleasedWhenClosed = false
        window.delegate = self
        title.font = .boldSystemFont(ofSize: 14)
        text.preferredMaxLayoutWidth = 400
        buttons.orientation = .horizontal
        buttons.spacing = 8
        let stack = NSStackView(views: [title, text, buttons])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 18, left: 20, bottom: 18, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = NSView()
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            text.widthAnchor.constraint(equalToConstant: 400),
        ])
        window.contentView = content
        say(Texte.t("fenster"))
        window.center()
        show()
    }

    /// Neuer Stand mit „Schließen“ und höchstens zwei Knöpfen davor (der erste ist der vorgeschlagene).
    func say(_ s: String, title t: String? = nil, extra: (String, @MainActor () -> Void)? = nil,
             second: (String, @MainActor () -> Void)? = nil) {
        title.stringValue = t ?? Texte.t("fenster")
        text.stringValue = s
        buttons.arrangedSubviews.forEach { $0.removeFromSuperview() }
        actions = []
        for (label, action) in [extra, second].compactMap({ $0 }) {
            let b = NSButton(title: label, target: self, action: #selector(clicked(_:)))
            b.bezelStyle = .rounded
            b.tag = actions.count
            actions.append(action)
            buttons.addArrangedSubview(b)
        }
        let close = NSButton(title: Texte.t("schliessen"), target: self, action: #selector(closeClicked))
        close.bezelStyle = .rounded
        buttons.addArrangedSubview(close)
        (buttons.arrangedSubviews.first as? NSButton)?.keyEquivalent = "\r"
        window.contentView?.layoutSubtreeIfNeeded()
        if let size = window.contentView?.fittingSize { window.setContentSize(size) }
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func hide() {
        window.orderOut(nil)
    }

    @objc private func clicked(_ b: NSButton) {
        if actions.indices.contains(b.tag) { actions[b.tag]() }
    }

    @objc private func closeClicked() {
        window.close()
    }

    func windowWillClose(_ notification: Notification) {
        onClose()
    }
}
