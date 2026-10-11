import AVFoundation
import AppKit
import SwiftUI

extension Windows {
    static func showSettings() {
        if Windows.shared.isOpen("settings") {
            Windows.shared.show("settings", title: "", size: .zero) { EmptyView() }   // only brings it to the front
            return
        }
        let recorder = HotkeyRecorder()
        Windows.shared.show("settings", title: "Spark-Begleiter – Einstellungen", size: NSSize(width: 580, height: 600)) {
            SettingsView(model: AppModel.shared, recorder: recorder, updater: Updater.shared)
        }
        Windows.shared.whenClosed("settings") { recorder.stop() }
    }
}

/// The program's own settings: the connection, the hotkeys (only here, never on the Spark), the permissions.
/// Which parts are on is set in the panel.
struct SettingsView: View {
    enum Tab: String, CaseIterable, Identifiable {
        case allgemein = "Allgemein"
        case kuerzel = "Tastenkürzel"
        case ueber = "Über"
        var id: String { rawValue }
    }

    @ObservedObject var model: AppModel
    @ObservedObject var recorder: HotkeyRecorder
    @ObservedObject var updater: Updater
    @State private var axTrusted = false
    @State private var mic: AVAuthorizationStatus = .notDetermined
    @State private var screenOK = false
    @ObservedObject private var folder = FolderWatch.shared
    @State private var tab: Tab = .allgemein

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            Picker("", selection: $tab) {
                ForEach(Tab.allCases) { t in
                    Text(verbatim: t.rawValue).tag(t)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 360)
            .padding(.top, 12)
            .padding(.horizontal, 16)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    switch tab {
                    case .allgemein: general
                    case .kuerzel: shortcuts
                    case .ueber: about
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Theme.bg)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 500, minHeight: 460)
        .onAppear { refreshPermissions() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissions()
        }
        .onChange(of: tab) { _ in recorder.stop() }
    }

    // ------------------------------------------------------------------ Allgemein

    @ViewBuilder
    private var general: some View {
        section("Verbindung") {
            if let base = model.base {
                Text(verbatim: "Gekoppelt mit \(base)")
                    .textSelection(.enabled)
                if let p = model.config?.profile, !p.isEmpty {
                    Text(verbatim: "Profil: \(p)")
                        .foregroundColor(Theme.muted)
                }
                Text(verbatim: model.statusLine)
                    .foregroundColor(Theme.muted)
            } else {
                Text(verbatim: "Nicht gekoppelt.")
            }
            HStack {
                Button("Panel öffnen") { model.openPanel() }
                    .disabled(model.base == nil)
                Button("Neu koppeln …") { Windows.showPairing() }
                Button("Entkoppeln …") { confirmUnpair() }
                    .disabled(!model.paired)
            }
        }
        generalRest
    }

    // ------------------------------------------------------------------ Tastenkürzel

    @ViewBuilder
    private var shortcuts: some View {
        section("Tastenkürzel") {
            ForEach(HotAction.allCases) { a in
                HStack {
                    Text(verbatim: a.title)
                        .frame(width: 120, alignment: .leading)
                    Button {
                        if recorder.recording == a { recorder.stop() } else { recorder.start(a) }
                    } label: {
                        Text(verbatim: recorder.recording == a ? "Tasten drücken …" : (model.hotkeys[a]?.label ?? "–"))
                            .frame(minWidth: 130)
                    }
                    Button("Standard") {
                        recorder.stop()
                        recorder.hint = model.setHotkey(a, a.standard) ?? ""
                    }
                    if model.paired && model.config != nil && !model.part(a.part) {
                        Text(verbatim: "(im Panel aus)")
                            .font(.caption)
                            .foregroundColor(Theme.muted)
                    }
                }
            }
            if !recorder.hint.isEmpty {
                Text(verbatim: recorder.hint)
                    .font(.caption)
                    .foregroundColor(recorder.recording == nil ? Theme.bad : Theme.muted)
            }
            if !model.hotkeyProblem.isEmpty {
                Text(verbatim: model.hotkeyProblem)
                    .font(.caption)
                    .foregroundColor(Theme.bad)
            }
            Text(verbatim: "Ein Kürzel braucht ⌘, ⌥ oder ⌃. Die Kürzel gelten nur auf diesem Mac.")
                .font(.caption)
                .foregroundColor(Theme.muted)
        }

    }

    @ViewBuilder
    private var generalRest: some View {
        permissions
        if model.part("folder") { folderSettings }
        panelSettings
    }

    @ViewBuilder
    private var folderSettings: some View {
        section("Ordner „Spark-Wissen“") {
            Text(verbatim: folder.path.path)
                .font(.system(size: 12, design: .monospaced))
                .textSelection(.enabled)
            HStack {
                Button("Anderen Ordner wählen …") { folder.chooseFolder() }
                Button("Im Finder zeigen") { folder.reveal() }
                if folder.path != FolderWatch.defaultPath {
                    Button("Standard") { folder.setPath(FolderWatch.defaultPath) }
                }
            }
            if !folder.lastText.isEmpty {
                Text(verbatim: folder.lastText)
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            }
            Text(verbatim: "Neue oder geänderte Dateien (PDF, Word, Excel, PowerPoint, Text, Bilder …) kommen ins Wissen des Spark, sobald sie 10 Sekunden lang nicht mehr geändert wurden – höchstens 50 am Tag. Versteckte und halbfertige Dateien bleiben liegen.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var permissions: some View {
        section("Berechtigungen") {
            HStack {
                Text(verbatim: axTrusted ? "Bedienungshilfen: erlaubt" : "Bedienungshilfen: nicht erlaubt")
                Spacer()
                if !axTrusted {
                    Button("Erlauben …") {
                        Access.explainAndAsk()
                        axTrusted = Access.trusted
                    }
                }
            }
            Text(verbatim: "Nötig, damit der Begleiter markierten Text kopieren und das Ergebnis einfügen kann (⌘C/⌘V). Ohne: Text ins Fenster einfügen, das Ergebnis liegt in der Zwischenablage. „Mit Spark verbessern“ im Dienste-Menü geht immer.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Text(verbatim: micText)
                Spacer()
                if mic != .authorized {
                    Button("Erlauben …") {
                        if mic == .notDetermined {
                            Task { @MainActor in
                                _ = await Recorder.micAllowed()
                                mic = AVCaptureDevice.authorizationStatus(for: .audio)
                            }
                        } else {
                            Recorder.openMicSettings()
                        }
                    }
                }
            }
            if model.part("dictate") || model.part("wake") {
                Text(verbatim: "Nötig fürs Diktieren und das Weckwort.")
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            }
            if model.part("screen") {
                HStack {
                    Text(verbatim: screenOK ? "Bildschirmaufnahme: erlaubt" : "Bildschirmaufnahme: nicht erlaubt")
                    Spacer()
                    if !screenOK {
                        Button("Erlauben …") { ScreenAsk.explainPermission() }
                    }
                }
                Text(verbatim: "Nötig für „Bildschirm fragen“ (⌥⌘B). Nach dem Erlauben den Begleiter neu starten.")
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            }
            if model.part("mail") {
                HStack {
                    Text(verbatim: "Automation → Mail")
                    Spacer()
                    Button("Einstellungen öffnen") {
                        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
                            NSWorkspace.shared.open(url)
                        }
                    }
                }
                Text(verbatim: "macOS fragt beim ersten „Antwort entwerfen“, ob der Begleiter Mail steuern darf. Er liest nur die ausgewählte Mail und öffnet einen Entwurf; er sendet nie.")
                    .font(.caption)
                    .foregroundColor(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }

    }

    @ViewBuilder
    private var panelSettings: some View {
        section("Im Panel eingestellt") {
            if let cfg = model.config {
                ForEach(DeskConfig.partNames, id: \.self) { p in
                    HStack {
                        Image(systemName: cfg.parts[p] == true ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(cfg.parts[p] == true ? Theme.ok : Theme.muted)
                        Text(verbatim: Self.partTitle(p))
                        if cfg.parts[p] != true && cfg.allowed[p] != true {
                            Text(verbatim: "(nicht freigegeben)")
                                .font(.caption)
                                .foregroundColor(Theme.muted)
                        }
                    }
                }
                Text(verbatim: model.autostartOn ? "Autostart: an" : "Autostart: aus")
                if !model.autostartProblem.isEmpty {
                    Text(verbatim: model.autostartProblem)
                        .font(.caption)
                        .foregroundColor(Theme.bad)
                }
                Text(verbatim: "Ändern im Panel unter Ich → Begleiter; der Begleiter übernimmt es beim nächsten Abruf.")
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            } else {
                Text(verbatim: "Noch keine Einstellungen vom Spark.")
                    .foregroundColor(Theme.muted)
            }
        }

    }

    // ------------------------------------------------------------------ Über

    private var archText: String {
        #if arch(arm64)
        return "Mac · Apple-Chip"
        #else
        return "Mac · Intel"
        #endif
    }

    private var updatePill: (String, Color) {
        if Updater.currentVersion == nil { return (updater.statusText, Theme.muted) }
        switch updater.phase {
        case .idle: return ("Neueste Version", Theme.ok)
        case .failed: return ("Update fehlgeschlagen", Theme.bad)
        default: return (updater.statusText, Theme.accent)
        }
    }

    @ViewBuilder
    private var about: some View {
        CardBox {
            HStack(spacing: 12) {
                FaceView(size: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: "Spark-Begleiter \(model.version)")
                        .font(.system(size: 15, weight: .semibold))
                        .textSelection(.enabled)
                    Text(verbatim: archText + (model.base.map { " · gekoppelt mit " + SparkAddress.host(of: $0) } ?? " · nicht gekoppelt"))
                        .font(.system(size: 12))
                        .foregroundColor(Theme.muted)
                        .textSelection(.enabled)
                }
            }
            HStack(spacing: 8) {
                let pill = updatePill
                StatusPill(text: pill.0, color: pill.1)
                Button("Nach Updates suchen") { Task { await updater.check() } }
                    .buttonStyle(SoftButtonStyle())
                    .disabled(!model.paired || updater.checking || Updater.currentVersion == nil)
                if updater.checking { ProgressView().controlSize(.small) }
            }
            if updater.dot, let info = updater.info {
                UpdateBanner(info: info, updater: updater)
            }
            if let t = updater.lastCheck {
                Text(verbatim: "Zuletzt gefragt: " + Self.timeFormat.string(from: t))
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
            }
            Toggle(isOn: $updater.autoLoad) {
                Text(verbatim: "Updates automatisch laden, vor dem Installieren fragen")
            }
            .toggleStyle(.checkbox)
            Text(verbatim: "Updates kommen nur von deinem eigenen Spark und werden vor dem Einspielen mit Größe und Prüfsumme (SHA-256) geprüft. Installiert wird erst nach deinem Klick auf „Aktualisieren“.")
                .font(.system(size: 11))
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        CardBox {
            Text(verbatim: "Der Spark ist kostenlos. Wenn er dir hilft, freut sich der Entwickler über einen Kaffee.")
                .font(.system(size: 12))
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
            CoffeePill(title: "Buy me a coffee", url: model.coffee)
        }
    }

    private static let timeFormat: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateStyle = .none
        f.timeStyle = .short
        return f
    }()

    private func refreshPermissions() {
        axTrusted = Access.trusted
        mic = AVCaptureDevice.authorizationStatus(for: .audio)
        screenOK = ScreenAsk.permitted
    }

    private var micText: String {
        switch mic {
        case .authorized: return "Mikrofon: erlaubt"
        case .notDetermined: return "Mikrofon: noch nicht gefragt"
        default: return "Mikrofon: nicht erlaubt"
        }
    }

    static func partTitle(_ p: String) -> String {
        switch p {
        case "write": return "Schreibhilfe"
        case "ask": return "Frag Spark"
        case "dictate": return "Diktieren"
        case "notes": return "Meldungen"
        case "status": return "Zustandspunkt"
        case "notaus": return "Mein-Notaus-Knopf"
        case "files": return "Rechtsklick auf Dateien"
        case "screen": return "Bildschirm fragen"
        case "context": return "App erkennen"
        case "mail": return "Antwort entwerfen (Mail)"
        case "folder": return "Ordner „Spark-Wissen“ beobachten"
        case "actions": return "Knöpfe in Meldungen"
        case "act": return "Spark darf am Mac handeln"
        case "wake": return "Weckwort"
        default: return p
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        let inner = content()
        return CardBox {
            Text(verbatim: title)
                .font(.headline)
            inner
        }
    }

    private func confirmUnpair() {
        let a = NSAlert()
        a.messageText = "Entkoppeln?"
        a.informativeText = "Der Schlüssel wird von diesem Mac gelöscht. Im Panel unter Ich → Begleiter das Gerät auch entfernen, dann ist der Schlüssel ganz weg."
        a.addButton(withTitle: "Entkoppeln")
        a.addButton(withTitle: "Abbrechen")
        if a.runModal() == .alertFirstButtonReturn {
            model.unpair()
        }
    }
}
