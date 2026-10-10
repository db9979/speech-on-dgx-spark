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
        Windows.shared.show("settings", title: "Spark-Begleiter – Einstellungen", size: NSSize(width: 560, height: 560)) {
            SettingsView(model: AppModel.shared, recorder: recorder)
        }
        Windows.shared.whenClosed("settings") { recorder.stop() }
    }
}

/// The program's own settings: the connection, the hotkeys (only here, never on the Spark), the permissions.
/// Which parts are on is set in the panel.
struct SettingsView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var recorder: HotkeyRecorder
    @State private var axTrusted = false
    @State private var mic: AVAuthorizationStatus = .notDetermined

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                section("Verbindung") {
                    if let base = model.base {
                        Text(verbatim: "Gekoppelt mit \(base)")
                            .textSelection(.enabled)
                        if let p = model.config?.profile, !p.isEmpty {
                            Text(verbatim: "Profil: \(p)")
                                .foregroundColor(.secondary)
                        }
                        Text(verbatim: model.statusLine)
                            .foregroundColor(.secondary)
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
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    if !recorder.hint.isEmpty {
                        Text(verbatim: recorder.hint)
                            .font(.caption)
                            .foregroundColor(recorder.recording == nil ? .red : .secondary)
                    }
                    if !model.hotkeyProblem.isEmpty {
                        Text(verbatim: model.hotkeyProblem)
                            .font(.caption)
                            .foregroundColor(.red)
                    }
                    Text(verbatim: "Ein Kürzel braucht ⌘, ⌥ oder ⌃. Die Kürzel gelten nur auf diesem Mac.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

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
                        .foregroundColor(.secondary)
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
                }

                section("Im Panel eingestellt") {
                    if let cfg = model.config {
                        ForEach(DeskConfig.partNames, id: \.self) { p in
                            HStack {
                                Image(systemName: cfg.parts[p] == true ? "checkmark.circle.fill" : "circle")
                                    .foregroundColor(cfg.parts[p] == true ? .green : .secondary)
                                Text(verbatim: Self.partTitle(p))
                                if cfg.parts[p] != true && cfg.allowed[p] != true {
                                    Text(verbatim: "(nicht freigegeben)")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }
                        Text(verbatim: model.autostartOn ? "Autostart: an" : "Autostart: aus")
                        if !model.autostartProblem.isEmpty {
                            Text(verbatim: model.autostartProblem)
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                        Text(verbatim: "Ändern im Panel unter Ich → Begleiter; der Begleiter übernimmt es beim nächsten Abruf.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text(verbatim: "Noch keine Einstellungen vom Spark.")
                            .foregroundColor(.secondary)
                    }
                }

                Text(verbatim: "Spark-Begleiter \(model.version)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minWidth: 480, minHeight: 420)
        .onAppear { refreshPermissions() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissions()
        }
    }

    private func refreshPermissions() {
        axTrusted = Access.trusted
        mic = AVCaptureDevice.authorizationStatus(for: .audio)
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
        default: return p
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(verbatim: title)
                .font(.headline)
            content()
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
