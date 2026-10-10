import AppKit
import SwiftUI

/// Spark-Begleiter: a small program in the menu bar (no Dock icon, LSUIElement) for the own Spark.
@main
@MainActor
struct SparkBegleiterApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @ObservedObject private var model: AppModel
    @ObservedObject private var dictation: Dictation

    init() {
        _model = ObservedObject(wrappedValue: AppModel.shared)
        _dictation = ObservedObject(wrappedValue: Dictation.shared)
    }

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: model, dictation: dictation)
        } label: {
            Image(nsImage: dictation.recording ? AppModel.recordingIcon : model.menuIcon)
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let services = ServiceProvider()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.servicesProvider = services
        NSUpdateDynamicServices()
        AppModel.shared.start()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}

extension AppModel {
    static var recordingIcon: NSImage {
        let img = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Aufnahme läuft") ?? NSImage()
        let colored = img.withSymbolConfiguration(NSImage.SymbolConfiguration(paletteColors: [.systemRed])) ?? img
        colored.isTemplate = false
        return colored
    }
}

/// The menu of the menu-bar icon. A part that is off but allowed shows greyed with the hint; one that is not
/// allowed at all does not show.
struct MenuContent: View {
    @ObservedObject var model: AppModel
    @ObservedObject var dictation: Dictation

    var body: some View {
        Text(verbatim: model.statusLine)
        Divider()
        if model.paired {
            item("write", "Text verbessern", .write) {
                Task { await model.startWrite(fromMenu: true) }
            }
            item("ask", "Frag Spark …", .ask) {
                model.openAsk()
            }
            item("dictate", dictation.recording ? "Diktat beenden" : "Diktieren", .dictate) {
                dictation.toggle(.cursor(nil))
            }
            if model.part("notaus") {
                Divider()
                Button("Mein Notaus auslösen …") { model.confirmNotaus() }
            }
            Divider()
            Button("Panel öffnen") { model.openPanel() }
        } else {
            Button("Koppeln …") { Windows.showPairing() }
        }
        Button("Einstellungen …") { Windows.showSettings() }
        Divider()
        Button("Spark-Begleiter beenden") { NSApp.terminate(nil) }
    }

    @ViewBuilder
    private func item(_ part: String, _ title: String, _ action: HotAction, run: @escaping () -> Void) -> some View {
        if model.part(part) {
            let key = model.hotkeyLabel(action)
            let label: String = key.isEmpty ? title : title + "  (" + key + ")"
            Button(label) { run() }
        } else if model.allowedPart(part) {
            let label: String = title + " – im Panel unter Ich → Begleiter einschalten"
            Button(label) {}
                .disabled(true)
        }
    }
}

/// "Mit Spark verbessern" in the Services menu (and the context menu of marked text): macOS hands over the marked
/// text and puts back what we return. Needs no Accessibility permission.
@MainActor
final class ServiceProvider: NSObject {
    @objc(improveText:userData:error:)
    func improveText(_ pboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        let model = AppModel.shared
        let previous = NSWorkspace.shared.frontmostApplication
        guard let text = pboard.string(forType: .string),
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            error.pointee = "Kein Text markiert." as NSString
            HUD.show("Erst Text markieren, dann „Mit Spark verbessern“.")
            return
        }
        guard model.paired else {
            error.pointee = "Nicht gekoppelt." as NSString
            Windows.showPairing()
            return
        }
        if model.config != nil && !model.part("write") {
            error.pointee = "Die Schreibhilfe ist aus." as NSString
            HUD.show(AppModel.offHint("Die Schreibhilfe"))
            return
        }
        let result = WriteController.runForService(text: text, config: model.config ?? DeskConfig())
        if let result {
            pboard.clearContents()
            pboard.setString(result, forType: .string)
        } else {
            error.pointee = "Abgebrochen." as NSString
        }
        if let previous, previous != NSRunningApplication.current {
            previous.activate(options: [])
        }
    }
}
