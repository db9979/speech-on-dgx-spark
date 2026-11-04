import AppKit
import ApplicationServices
import CoreGraphics

// SparkHilfe für den Mac (Spontanhilfe S2c, plan spontanhilfe/s2-plan.md): das kleine Programm, das eine Person einmal
// öffnet, damit ihr Helfer ihren Mac steuern darf. Keine Installation, keine Einstellungen, keine Argumente, nichts auf
// der Platte: nur der Name der eigenen App zählt (Ziel.swift). Erst führt ein kleiner Assistent zu den zwei Freigaben
// (Bildschirmaufnahme, Bedienungshilfen) und öffnet jeweils die richtige Seite der Systemeinstellungen; erst danach
// verbindet es sich (der Einmal-Schlüssel bleibt bis dahin unbenutzt, ein Neustart nach der Freigabe geht also). Dann
// fragt es selbst, zeigt roten Rahmen und Leiste und endet mit „Beenden“, dem Schließen des Fensters oder ⌘Q.

@main
enum SparkHilfeMain {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var status: StatusFenster?
    private var sitzung: Sitzung?
    private var weiterOhne = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        menu()
        let id = Bundle.main.bundleIdentifier ?? ""
        if NSRunningApplication.runningApplications(withBundleIdentifier: id).count > 1 {
            _ = ViewAlert.ask(message: Texte.t("laeuft_schon"), info: "", buttons: [Texte.t("schliessen")], timeout: 60)
            NSApp.terminate(nil)
            return
        }
        let status = StatusFenster { NSApp.terminate(nil) }
        self.status = status
        NSApp.activate(ignoringOtherApps: true)
        Task { @MainActor in await self.start(status) }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let s = sitzung, s.running else { return .terminateNow }
        s.stop { NSApp.reply(toApplicationShouldTerminate: true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }

    private func start(_ status: StatusFenster) async {
        guard let ziel = Ziel.ausProgramm() else {
            status.say(Texte.t("name_falsch"))
            return
        }
        // Schritt 1: ohne Bildschirmaufnahme gibt es kein Bild; der Schlüssel bleibt unbenutzt (neu öffnen geht)
        if !CGPreflightScreenCaptureAccess() {
            status.say(Texte.t("fehlt_bild"), title: Texte.t("schritt1"),
                       extra: (Texte.t("einstellungen"), {
                           _ = CGRequestScreenCaptureAccess()
                           Self.open("Privacy_ScreenCapture")
                       }))
            while !CGPreflightScreenCaptureAccess() {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
        // Schritt 2: ohne Bedienungshilfen geht nur Ansehen
        if !AXIsProcessTrusted() {
            status.say(Texte.t("fehlt_bedienen"), title: Texte.t("schritt2"),
                       extra: (Texte.t("einstellungen"), {
                           // the value of kAXTrustedCheckOptionPrompt: macOS adds SparkHilfe to the list
                           _ = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
                           Self.open("Privacy_Accessibility")
                       }),
                       second: (Texte.t("ohne"), { [weak self] in self?.weiterOhne = true }))
            while !AXIsProcessTrusted() && !weiterOhne {
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
        status.say(Texte.t("verbinde", host: ziel.shown))
        let s = Sitzung(ziel: ziel, status: status)
        sitzung = s
        let ende = await s.run()
        sitzung = nil
        if ende.isEmpty {
            NSApp.terminate(nil)
            return
        }
        status.say(ende)
        status.show()
    }

    /// the page of System Settings → Privacy & Security for one permission (fixed names only)
    private static func open(_ pane: String) {
        guard ["Privacy_ScreenCapture", "Privacy_Accessibility"].contains(pane),
              let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?" + pane) else { return }
        NSWorkspace.shared.open(url)
    }

    /// the app menu with „SparkHilfe beenden“ (⌘Q) only
    private func menu() {
        let main = NSMenu()
        let item = NSMenuItem()
        main.addItem(item)
        let sub = NSMenu()
        sub.addItem(withTitle: Texte.t("beenden"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = sub
        NSApp.mainMenu = main
    }
}
