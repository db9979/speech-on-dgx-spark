import AppKit
import SwiftUI

/// Spark-Begleiter: a small program in the menu bar (no Dock icon, LSUIElement) for the own Spark.
@main
@MainActor
struct SparkBegleiterApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @ObservedObject private var model: AppModel
    @ObservedObject private var dictation: Dictation
    @ObservedObject private var updater: Updater
    @ObservedObject private var wake: Wake
    @ObservedObject private var quiet: Quiet
    @ObservedObject private var meeting: Meeting
    @ObservedObject private var mic = MicSwitch.shared

    init() {
        _model = ObservedObject(wrappedValue: AppModel.shared)
        _dictation = ObservedObject(wrappedValue: Dictation.shared)
        _updater = ObservedObject(wrappedValue: Updater.shared)
        _wake = ObservedObject(wrappedValue: Wake.shared)
        _quiet = ObservedObject(wrappedValue: Quiet.shared)
        _meeting = ObservedObject(wrappedValue: Meeting.shared)
    }

    var body: some Scene {
        MenuBarExtra {
            TrayPanel(model: model, dictation: dictation, updater: updater, wake: wake, folder: FolderWatch.shared)
        } label: {
            Image(nsImage: dictation.recording || meeting.running ? AppModel.recordingIcon : menuIcon)
        }
        .menuBarExtraStyle(.window)
    }

    /// read here so the label follows the model and the updater
    private var menuIcon: NSImage {
        _ = updater.phase
        _ = wake.listening
        _ = quiet.busy
        _ = mic.closed
        return model.menuIcon
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
        let category = previous == NSRunningApplication.current ? nil : model.appCategory(previous)
        let result = WriteController.runForService(text: text, config: model.config ?? DeskConfig(), app: category)
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
