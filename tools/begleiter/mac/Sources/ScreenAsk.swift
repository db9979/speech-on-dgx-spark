import AppKit
import CoreGraphics
import SwiftUI

/// Part "screen" (⌥⌘B): drag a region with macOS's own screencapture, then a small box for an optional question.
/// The picture lives only in memory: the temporary file (in a private folder) is deleted right after reading.
@MainActor
enum ScreenAsk {
    static let windowID = "screen"
    private static var running = false

    static func start() {
        let model = AppModel.shared
        guard model.paired else {
            Windows.showPairing()
            return
        }
        guard model.part("screen") else {
            HUD.show(AppModel.offHint("Bildschirm fragen"))
            return
        }
        guard !running else { return }
        guard CGPreflightScreenCaptureAccess() else {
            explainPermission()
            return
        }
        running = true
        Windows.shared.close(windowID)
        Task { @MainActor in
            defer { running = false }
            guard let raw = await capture() else { return }          // Esc: nothing taken
            let prepared = await Task.detached(priority: .userInitiated) { prepare(raw) }.value
            guard let prepared, let thumb = NSImage(data: prepared.0) else {
                HUD.show("Das Bild ließ sich nicht verkleinern (höchstens 6 MB).", symbol: "exclamationmark.triangle")
                return
            }
            ScreenBox.show(image: prepared.0, type: prepared.1, thumbnail: thumb)
        }
    }

    static var permitted: Bool { CGPreflightScreenCaptureAccess() }

    static func openSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }

    static func explainPermission() {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Bildschirmaufnahme erlauben?"
        a.informativeText = """
            Für „Bildschirm fragen“ braucht der Spark-Begleiter die Freigabe „Bildschirmaufnahme“ \
            (Systemeinstellungen → Datenschutz & Sicherheit → Bildschirm- & Systemaudioaufnahme).

            Aufgenommen wird nur der Bereich, den du nach ⌥⌘B selbst aufziehst, und nur zu deinem eigenen Spark \
            geschickt. Nach dem Erlauben den Begleiter einmal beenden und neu starten.
            """
        a.addButton(withTitle: "Freigabe öffnen")
        a.addButton(withTitle: "Später")
        if a.runModal() == .alertFirstButtonReturn {
            if !CGRequestScreenCaptureAccess() { openSettings() }
        }
    }

    /// `screencapture -i -x <file>` (interactive region, no sound); nil when the person pressed Esc.
    static func capture() async -> Data? {
        let fm = FileManager.default
        let dir = fm.temporaryDirectory.appendingPathComponent("spark-bildschirm-" + UUID().uuidString, isDirectory: true)
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        } catch {
            HUD.show("Kein Platz für die Bildschirmaufnahme.", symbol: "exclamationmark.triangle")
            return nil
        }
        defer { try? fm.removeItem(at: dir) }
        let file = dir.appendingPathComponent("bereich.png")
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        p.arguments = ["-i", "-x", file.path]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        let started: Bool = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            p.terminationHandler = { _ in cont.resume(returning: true) }
            do {
                try p.run()
            } catch {
                p.terminationHandler = nil
                cont.resume(returning: false)
            }
        }
        guard started else {
            HUD.show("Die Bildschirmaufnahme ließ sich nicht starten.", symbol: "exclamationmark.triangle")
            return nil
        }
        guard fm.fileExists(atPath: file.path) else { return nil }
        let data = try? Data(contentsOf: file)
        try? fm.removeItem(at: file)
        guard let data, !data.isEmpty else { return nil }
        return data
    }

    /// Long side ≤ 2000 px, PNG ≤ 6 MB (else JPEG, else smaller). Re-encoded, so no metadata goes along.
    nonisolated static func prepare(_ raw: Data) -> (Data, String)? {
        guard let rep = NSBitmapImageRep(data: raw), rep.pixelsWide > 0, rep.pixelsHigh > 0 else { return nil }
        var size = ScreenShot.fit(width: rep.pixelsWide, height: rep.pixelsHigh)
        for _ in 0..<5 {
            guard let scaled = scale(rep, width: size.width, height: size.height) else { return nil }
            if let png = scaled.representation(using: .png, properties: [:]), png.count <= ScreenShot.maxBytes {
                return (png, "image/png")
            }
            if let jpg = scaled.representation(using: .jpeg, properties: [.compressionFactor: 0.85]),
               jpg.count <= ScreenShot.maxBytes {
                return (jpg, "image/jpeg")
            }
            size = (max(1, size.width * 7 / 10), max(1, size.height * 7 / 10))
        }
        return nil
    }

    nonisolated private static func scale(_ rep: NSBitmapImageRep, width: Int, height: Int) -> NSBitmapImageRep? {
        guard let out = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: out) else { return nil }
        out.size = NSSize(width: width, height: height)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        ctx.imageInterpolation = .high
        rep.draw(in: NSRect(x: 0, y: 0, width: width, height: height), from: .zero, operation: .copy, fraction: 1,
                 respectFlipped: false, hints: nil)
        ctx.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        return out
    }
}

/// The box after the region: what should happen (chips) and an optional question.
@MainActor
final class ScreenBox: ObservableObject {
    @Published var what = "erklaeren"
    @Published var question = ""

    let image: Data
    let type: String
    let thumbnail: NSImage

    init(image: Data, type: String, thumbnail: NSImage) {
        self.image = image
        self.type = type
        self.thumbnail = thumbnail
    }

    static func show(image: Data, type: String, thumbnail: NSImage) {
        let box = ScreenBox(image: image, type: type, thumbnail: thumbnail)
        Windows.shared.show(ScreenAsk.windowID, title: "Bildschirm fragen", size: NSSize(width: 460, height: 420),
                            floating: true) {
            ScreenBoxView(box: box)
        }
    }

    func send() {
        let q = question.trimmingCharacters(in: .whitespacesAndNewlines)
        let w = what
        let title = ScreenShot.whats.first(where: { $0.id == w })?.title ?? "Erklären"
        let img = image
        let t = type
        Windows.shared.close(ScreenAsk.windowID)
        AskController.shared.run(question: "Bildschirm · " + title + (q.isEmpty ? "" : ": " + q)) { client in
            try await client.screen(img, type: t, question: String(q.prefix(ScreenShot.maxQuestion)), what: w)
        }
    }
}

struct ScreenBoxView: View {
    @ObservedObject var box: ScreenBox

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    FaceView(size: 28)
                    Text(verbatim: "Bildschirm fragen")
                        .font(.system(size: 14, weight: .semibold))
                    Spacer()
                }
                Image(nsImage: box.thumbnail)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: 180)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Theme.soft))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                    .accessibilityLabel(Text(verbatim: "Der aufgenommene Bereich"))
                HStack(spacing: 6) {
                    ForEach(0..<ScreenShot.whats.count, id: \.self) { i in
                        let w = ScreenShot.whats[i]
                        ChipButton(title: w.title, selected: box.what == w.id) { box.what = w.id }
                    }
                }
                HStack(alignment: .bottom, spacing: 6) {
                    TextField("Frage dazu (freiwillig) …", text: $box.question, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .lineLimit(1...4)
                        .onSubmit { box.send() }
                    FieldMic(id: "screen.question", label: "Frage") { t in
                        box.question = Dictation.append(t, to: box.question, max: ScreenShot.maxQuestion)
                    }
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                HStack {
                    Text(verbatim: "Geht nur an deinen Spark.")
                        .font(.system(size: 11))
                        .foregroundColor(Theme.muted)
                    Spacer()
                    Button("Abbrechen") { Windows.shared.close(ScreenAsk.windowID) }
                        .buttonStyle(SoftButtonStyle())
                        .keyboardShortcut(.cancelAction)
                    Button("Fragen") { box.send() }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(box.question.count > ScreenShot.maxQuestion)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 400, minHeight: 360)
    }
}
