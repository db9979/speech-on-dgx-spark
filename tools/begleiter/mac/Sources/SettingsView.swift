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
        Windows.shared.show("settings", title: "Spark-Begleiter – Einstellungen", size: NSSize(width: 760, height: 600)) {
            SettingsView(model: AppModel.shared, recorder: recorder, updater: Updater.shared)
        }
        Windows.shared.whenClosed("settings") { recorder.stop() }
    }
}

/// The program's own settings: the connection, the hotkeys (only here, never on the Spark), the permissions.
/// Which parts are on is set in the panel. A side menu like in the panel ("Begleiter aufpolieren" 2a,
/// Dominik 2026-10-17); a page only shows when its part is on.
struct SettingsView: View {
    enum Tab: String, CaseIterable, Identifiable {
        case uebersicht = "Übersicht"
        case frag = "Frag Spark"
        case kuerzel = "Tastenkürzel"
        case tagesstart = "Tagesstart"
        case ordner = "Wissen-Ordner"
        case rechte = "Berechtigungen"
        case kopplung = "Kopplung"
        case ueber = "Über und Update"
        var id: String { rawValue }

        var symbol: String {
            switch self {
            case .uebersicht: return "square.grid.2x2"
            case .frag: return "bubble.left"
            case .kuerzel: return "keyboard"
            case .tagesstart: return "sun.max"
            case .ordner: return "folder"
            case .rechte: return "lock.shield"
            case .kopplung: return "link"
            case .ueber: return "info.circle"
            }
        }

        var intro: String {
            switch self {
            case .uebersicht: return "Wie es dem Begleiter geht und was im Panel für ihn eingeschaltet ist."
            case .frag: return "Wie „Frag Spark“ auf diesem Mac antwortet."
            case .kuerzel: return "Die Tastenkürzel gelten nur auf diesem Mac."
            case .tagesstart: return "Ein kurzer Überblick am Morgen und zum Feierabend."
            case .ordner: return "Dateien aus diesem Ordner kommen ins Wissen des Spark."
            case .rechte: return "Was macOS dem Begleiter erlaubt."
            case .kopplung: return "Mit welchem Spark und Profil dieser Mac verbunden ist."
            case .ueber: return "Version, Updates und Unterstützung."
            }
        }

        /// the pages under the heading "GERÄT" in the side menu
        var device: Bool { self == .rechte || self == .kopplung || self == .ueber }
    }

    @ObservedObject var model: AppModel
    @ObservedObject var recorder: HotkeyRecorder
    @ObservedObject var updater: Updater
    @State private var axTrusted = false
    @State private var mic: AVAuthorizationStatus = .notDetermined
    @State private var screenOK = false
    @ObservedObject private var folder = FolderWatch.shared
    @ObservedObject private var daily = Daily.shared
    @AppStorage(AskSpeak.key) private var speakMode = "voice"
    @State private var tab: Tab = .uebersicht
    @State private var allParts = false

    /// pages of parts that are off stay out of the menu
    private var tabs: [Tab] {
        Tab.allCases.filter { t in
            switch t {
            case .frag: return model.part("speak")
            case .tagesstart: return model.part("daily")
            case .ordner: return model.part("folder")
            default: return true
            }
        }
    }

    private var current: Tab { tabs.contains(tab) ? tab : .uebersicht }

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            HStack(spacing: 0) {
                sidebar
                Rectangle().fill(Theme.line).frame(width: 1)
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(verbatim: current.rawValue)
                                .font(.system(size: 20, weight: .semibold))
                                .accessibilityAddTraits(.isHeader)
                            Text(verbatim: current.intro)
                                .font(.system(size: 12))
                                .foregroundColor(Theme.muted)
                        }
                        switch current {
                        case .uebersicht: overview
                        case .frag: speakSettings
                        case .kuerzel: shortcuts
                        case .tagesstart: dailySettings
                        case .ordner: folderSettings
                        case .rechte: permissions
                        case .kopplung: general
                        case .ueber: about
                        }
                    }
                    .padding(20)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .background(Theme.bg)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 660, minHeight: 460)
        .onAppear { refreshPermissions() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissions()
        }
        .onChange(of: tab) { _ in recorder.stop() }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                FaceView(size: 26)
                Text(verbatim: "Begleiter")
                    .font(.system(size: 14, weight: .semibold))
            }
            .padding(.horizontal, 6)
            .padding(.bottom, 10)
            ForEach(tabs.filter { !$0.device }) { t in
                NavRow(title: t.rawValue, symbol: t.symbol, selected: current == t) { tab = t }
            }
            SectionLabel(text: "Gerät")
                .padding(.top, 12)
                .padding(.bottom, 4)
                .padding(.horizontal, 6)
            ForEach(tabs.filter { $0.device }) { t in
                NavRow(title: t.rawValue, symbol: t.symbol, selected: current == t,
                       badge: t == .ueber && updater.dot ? "neu" : "") { tab = t }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(width: 200, alignment: .topLeading)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.soft)
    }

    // ------------------------------------------------------------------ Übersicht

    private var status: (title: String, color: Color, good: Bool) {
        guard model.paired else { return ("Nicht gekoppelt", Theme.muted, false) }
        switch model.reach {
        case .ok: return ("Alles läuft", Theme.ok, true)
        case .unknown: return ("Verbinde …", Theme.accent, true)
        case .offline: return ("Spark nicht erreichbar", Theme.warn, false)
        case .notaus: return ("Notaus ist an", Theme.bad, false)
        }
    }

    @ViewBuilder
    private var overview: some View {
        let s = status
        StatusCard(title: s.title, detail: model.statusLine, color: s.color, good: s.good)
        panelSettings
        panelLinks
    }

    // Sprung-Links ins Panel (Begleiter Paket A, Dominik 2026-10-30): no screens of their own, a click opens
    // <Spark>/#weg=<way> in the browser; Fernzugang only for a profile with the admin role (config.fern)
    static let wayData = "Ich → Sicherheit → Meine Daten"
    static let wayMemory = "Ich → Gedächtnis"
    static let wayFern = "Fernzugang → Systeme"

    @ViewBuilder
    private var panelLinks: some View {
        SectionLabel(text: "Im Panel")
        HStack(spacing: 8) {
            Button("Meine Daten") { model.openPanel(Wege.hash(Self.wayData)) }
            Button("Gedächtnis") { model.openPanel(Wege.hash(Self.wayMemory)) }
            if model.config?.fern == true {
                Button("Fernzugang") { model.openPanel(Wege.hash(Self.wayFern)) }
            }
        }
        .buttonStyle(SoftButtonStyle())
        .disabled(model.base == nil)
        Text(verbatim: "Öffnet das Panel im Browser an dieser Stelle.")
            .font(.caption)
            .foregroundColor(Theme.muted)
    }

    // ------------------------------------------------------------------ Kopplung

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
                Text(Wege.text(model.statusLine))
                    .foregroundColor(Theme.muted)
            } else {
                Text(verbatim: "Nicht gekoppelt.")
            }
            HStack(spacing: 8) {
                Button("Panel öffnen") { model.openPanel() }
                    .buttonStyle(SoftButtonStyle())
                    .disabled(model.base == nil)
                Button("Problem melden …") { model.openPanel("#melden") }
                    .buttonStyle(SoftButtonStyle())
                    .disabled(model.base == nil)
                Button("Neu koppeln …") { Windows.showPairing() }
                    .buttonStyle(SoftButtonStyle())
            }
        }
        section("Entkoppeln") {
            Text(verbatim: "Löscht den Schlüssel auf diesem Mac. Danach braucht der Begleiter einen neuen Kopplungscode.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
            Button("Entkoppeln …") { confirmUnpair() }
                .buttonStyle(SoftButtonStyle())
                .foregroundColor(Theme.bad)
                .disabled(!model.paired)
        }
    }

    // ------------------------------------------------------------------ Tastenkürzel

    @ViewBuilder
    private var shortcuts: some View {
        section("Kürzel") {
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
                Text(Wege.text(folder.lastText))
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            }
            Text(verbatim: "Neue oder geänderte Dateien (PDF, Word, Excel, PowerPoint, Text, Bilder …) kommen ins Wissen des Spark, sobald sie 10 Sekunden lang nicht mehr geändert wurden – höchstens 50 am Tag. Versteckte und halbfertige Dateien bleiben liegen.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// part daily: on/off and the times, only on this Mac
    @ViewBuilder
    private var dailySettings: some View {
        section("Tagesstart und Feierabend") {
            HStack {
                Toggle(isOn: $daily.morningOn) { Text(verbatim: "Tagesstart ab") }
                    .toggleStyle(.checkbox)
                DatePicker("", selection: timeBinding(\.morningMinutes), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                    .frame(width: 90)
                    .disabled(!daily.morningOn)
                Spacer()
                Button("Jetzt zeigen") { daily.run("morning", manual: true) }
            }
            HStack {
                Toggle(isOn: $daily.eveningOn) { Text(verbatim: "Feierabend ab") }
                    .toggleStyle(.checkbox)
                DatePicker("", selection: timeBinding(\.eveningMinutes), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                    .frame(width: 90)
                    .disabled(!daily.eveningOn)
                Spacer()
                Button("Jetzt zeigen") { daily.run("evening", manual: true) }
            }
            Text(verbatim: "Tagesstart: beim ersten Aufwachen oder Entsperren des Macs ab dieser Uhrzeit. Feierabend: beim Sperren des Bildschirms ab dieser Uhrzeit (die ersten Termine von morgen und offene Aufgaben). Je einmal am Tag, als Mitteilung und im Fenster von „Frag Spark“.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// part speak: whether the ask window reads its answers aloud (only on this Mac)
    @ViewBuilder
    private var speakSettings: some View {
        section("Vorlesen") {
            Picker(selection: $speakMode) {
                ForEach(AskSpeak.ids, id: \.self) { m in
                    Text(verbatim: AskSpeak.title(m)).tag(m)
                }
            } label: {
                Text(verbatim: "Antworten in „Frag Spark“ vorlesen")
            }
            .frame(maxWidth: 420)
            Text(verbatim: "Gesprochen heißt: mit dem Mikrofon im Fenster oder mit dem Weckwort gefragt. Eine neue Frage oder „Stopp“ beendet das Vorlesen. Markierten Text liest \(model.hotkeyLabel(.speak).isEmpty ? "das Kürzel" : model.hotkeyLabel(.speak)) vor.")
                .font(.caption)
                .foregroundColor(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// minutes of the day <-> a Date today, for the DatePicker
    private func timeBinding(_ key: ReferenceWritableKeyPath<Daily, Int>) -> Binding<Date> {
        Binding(
            get: {
                let m = daily[keyPath: key]
                return Calendar.current.date(bySettingHour: m / 60, minute: m % 60, second: 0, of: Date()) ?? Date()
            },
            set: { d in
                daily[keyPath: key] = Daily.clamp(DailyPlan.minuteOfDay(d))
            })
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
            if model.part("dictate") || model.part("wake") || model.part("meeting") {
                Text(verbatim: "Nötig fürs Diktieren, das Weckwort und das Mitschreiben von Besprechungen.")
                    .font(.caption)
                    .foregroundColor(Theme.muted)
            }
            if model.part("screen") || model.part("meeting") {
                HStack {
                    Text(verbatim: screenOK ? "Bildschirmaufnahme: erlaubt" : "Bildschirmaufnahme: nicht erlaubt")
                    Spacer()
                    if !screenOK {
                        Button("Erlauben …") { ScreenAsk.explainPermission() }
                    }
                }
                Text(verbatim: model.part("meeting")
                     ? "Nötig für „Bildschirm fragen“ und für den Ton des Macs beim Mitschreiben einer Besprechung (ohne: nur Mikrofon). Nach dem Erlauben den Begleiter neu starten."
                     : "Nötig für „Bildschirm fragen“ (⌥⌘B). Nach dem Erlauben den Begleiter neu starten.")
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

    /// what is set in the panel: the first six parts, the rest after "Weitere N zeigen"
    @ViewBuilder
    private var panelSettings: some View {
        SectionLabel(text: "Im Panel eingestellt")
        if let cfg = model.config {
            let names = DeskConfig.partNames
            let shown = allParts ? names : Array(names.prefix(6))
            PanelBox {
                ForEach(Array(shown.enumerated()), id: \.element) { i, p in
                    if i > 0 { RowLine() }
                    HStack(spacing: 10) {
                        Image(systemName: cfg.parts[p] == true ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(cfg.parts[p] == true ? Theme.ok : Theme.muted)
                            .frame(width: 20)
                        Text(verbatim: Self.partTitle(p))
                            .font(.system(size: 13))
                        Spacer(minLength: 6)
                        if cfg.parts[p] != true && cfg.allowed[p] != true {
                            Text(verbatim: "nicht freigegeben")
                                .font(.caption)
                                .foregroundColor(Theme.muted)
                        } else {
                            Text(verbatim: cfg.parts[p] == true ? "an" : "aus")
                                .font(.caption)
                                .foregroundColor(Theme.muted)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                }
            }
            if names.count > 6 {
                Button(allParts ? "Weniger zeigen" : "Weitere \(names.count - 6) zeigen") { allParts.toggle() }
                    .buttonStyle(.link)
            }
            Text(verbatim: model.autostartOn ? "Autostart: an" : "Autostart: aus")
                .font(.system(size: 12))
            if !model.autostartProblem.isEmpty {
                Text(verbatim: model.autostartProblem)
                    .font(.caption)
                    .foregroundColor(Theme.bad)
            }
            Text(Wege.text("Ändern im Panel unter Ich → Begleiter; der Begleiter übernimmt es beim nächsten Abruf."))
                .font(.caption)
                .foregroundColor(Theme.muted)
        } else {
            Text(verbatim: "Noch keine Einstellungen vom Spark.")
                .foregroundColor(Theme.muted)
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
        SectionLabel(text: "Spark unterstützen")
            .padding(.top, 4)
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
        case "speak": return "Vorlesen"
        case "inbox": return "Vom Handy auf den Mac"
        case "agenda": return "Termine im Begleiter"
        case "quiet": return "Nicht stören erkennen"
        case "meeting": return "Besprechung mitschreiben"
        case "home": return "Smart-Home-Knöpfe"
        case "daily": return "Tagesstart und Feierabend"
        case "post": return "Post im Begleiter"
        case "lists": return "Listen im Begleiter"
        case "capture": return "Schnell erfassen"
        case "offen": return "Offen im Begleiter"
        case "find": return "Finden im Begleiter"
        default: return p
        }
    }

    /// a small title in capitals above a card, like the panel's sections
    @ViewBuilder
    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        let inner = content()
        SectionLabel(text: title)
        CardBox {
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
