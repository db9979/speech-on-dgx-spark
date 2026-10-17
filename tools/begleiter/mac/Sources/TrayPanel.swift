import AppKit
import SwiftUI

/// Finds the window a SwiftUI view lives in (here: the MenuBarExtra's panel, to close it after a click).
struct WindowGrabber: NSViewRepresentable {
    let take: (NSWindow?) -> Void

    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async { [weak v] in take(v?.window) }
        return v
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async { [weak nsView] in take(nsView?.window) }
    }
}

/// The holder of the panel's window (a class, so setting it does not redraw the view).
final class PanelWindow {
    weak var window: NSWindow?

    @MainActor
    func close() {
        window?.close()
    }
}

/// Click on the face in the menu bar (design A): gradient bar, face with state, update banner, the parts that are
/// on with their hotkeys, "Mein Notaus …", and Einstellungen, Panel öffnen, Kaffee. Closes on focus loss and Esc.
struct TrayPanel: View {
    @ObservedObject var model: AppModel
    @ObservedObject var dictation: Dictation
    @ObservedObject var updater: Updater
    @ObservedObject var wake: Wake
    @ObservedObject var folder: FolderWatch
    @ObservedObject var speaker = Speaker.shared
    @ObservedObject var meeting = Meeting.shared
    @ObservedObject var quiet = Quiet.shared
    @ObservedObject var mic = MicSwitch.shared
    @ObservedObject var agenda = AgendaCenter.shared
    @ObservedObject var home = HomeCenter.shared
    @State private var holder = PanelWindow()

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 12) {
                header
                if !detail.isEmpty {
                    Text(verbatim: detail)
                        .font(.system(size: 12))
                        .foregroundColor(model.reach == .notaus ? Theme.bad : Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
                if updater.dot, let info = updater.info {
                    UpdateBanner(info: info, updater: updater)
                }
                if model.paired {
                    items
                    if model.part("agenda") { agendaSection }
                    if model.part("home") { homeSection }
                } else {
                    HStack {
                        Text(verbatim: "Noch nicht mit einem Spark gekoppelt.")
                            .font(.system(size: 13))
                            .foregroundColor(Theme.muted)
                        Spacer()
                        Button("Koppeln …") { go { Windows.showPairing() } }
                            .buttonStyle(PrimaryButtonStyle())
                    }
                }
                footer
            }
            .padding(14)
        }
        .frame(width: 360)
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .background(WindowGrabber { w in holder.window = w })
        .onExitCommand { holder.close() }
        .onAppear {
            agenda.refreshSoon()
            home.refreshSoon()
        }
    }

    // ------------------------------------------------------------------ parts of the panel

    private var subtitle: String {
        let p = model.config?.profile ?? ""
        return p.isEmpty ? model.deviceName : p + " · " + model.deviceName
    }

    /// the reason when the Spark is not reachable or a Notaus holds
    private var detail: String {
        guard model.paired, model.reach == .offline || model.reach == .notaus else { return "" }
        return model.reachText
    }

    private var header: some View {
        HStack(spacing: 12) {
            FaceView(size: 44)
            VStack(alignment: .leading, spacing: 1) {
                Text(verbatim: "Spark-Begleiter")
                    .font(.system(size: 14, weight: .semibold))
                Text(verbatim: subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(minWidth: 0)
            Spacer(minLength: 4)
            let pill = model.reachPill
            StatusPill(text: pill.text, color: pill.color)
            Button {
                NSApp.terminate(nil)
            } label: {
                Image(systemName: "power")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.muted)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(Text(verbatim: "Spark-Begleiter beenden"))
            .accessibilityLabel(Text(verbatim: "Spark-Begleiter beenden"))
        }
    }

    private var items: some View {
        VStack(spacing: 2) {
            partRow("write", "Text verbessern", symbol: "pencil", hotkey: .write) {
                Task { await model.startWrite(fromMenu: true) }
            }
            partRow("ask", "Frag Spark", symbol: "bubble.left", hotkey: .ask) {
                model.openAsk()
            }
            partRow("dictate", dictation.recording ? "Diktat beenden" : "Diktieren",
                    symbol: dictation.recording ? "stop.circle" : "mic", hotkey: .dictate) {
                dictation.toggle(.cursor(nil))
            }
            partRow("screen", "Bildschirm fragen", symbol: "viewfinder", hotkey: .screen) {
                ScreenAsk.start()
            }
            partRow("mail", "Antwort entwerfen", symbol: "envelope", hotkey: .mail) {
                MailDraft.start(front: nil)
            }
            partRow("office", "Office-Add-ins einrichten", symbol: "square.grid.2x2", hotkey: nil,
                    note: "Word, Excel und Outlook") {
                OfficeSetup.start(model: model)
            }
            partRow("act", "Am PC handeln einstellen", symbol: "hand.tap", hotkey: nil,
                    note: "Ohne Rückfrage, Kurzbefehle") {
                ActSettings.show()
            }
            partRow("folder", "Spark-Wissen-Ordner", symbol: "folder", hotkey: nil,
                    note: folder.lastText.isEmpty ? folder.path.lastPathComponent : folder.lastText) {
                folder.reveal()
            }
            partRow("speak", speaker.active ? "Vorlesen stoppen" : "Zwischenablage vorlesen",
                    symbol: speaker.active ? "stop.circle" : "speaker.wave.2", hotkey: .speak,
                    note: speaker.active ? "" : "Markierten Text: \(model.hotkeyLabel(.speak))") {
                if speaker.active { speaker.stop() } else { speaker.readClipboard() }
            }
            partRow("meeting", meeting.running ? "Besprechung beenden" : "Besprechung mitschreiben",
                    symbol: meeting.running ? "stop.circle" : "record.circle", hotkey: .meeting) {
                meeting.toggle()
            }
            partRow("inbox", "Vom Spark", symbol: "tray.and.arrow.down", hotkey: nil,
                    note: "Text, Links und Dateien vom Handy · Downloads/\(InboxCenter.folderName)") {
                InboxCenter.revealFolder()
            }
            partRow("quiet", "Nicht stören erkennen", symbol: quiet.busy ? "moon.fill" : "moon", hotkey: nil,
                    note: quiet.text) {
                quiet.check()
            }
            if model.usesMic {
                Button {
                    go { mic.toggle() }
                } label: {
                    HStack(spacing: 10) {
                        IconTile(symbol: mic.closed ? "mic.slash" : "mic", color: mic.closed ? Theme.bad : Theme.accent)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(verbatim: mic.closed ? "Mikrofon öffnen" : "Mikrofon schließen")
                                .font(.system(size: 13))
                            Text(verbatim: mic.closed ? "ist zu: nichts hört mit" : "ist offen")
                                .font(.system(size: 11))
                                .foregroundColor(mic.closed ? Theme.bad : Theme.muted)
                        }
                        Spacer()
                    }
                }
                .buttonStyle(RowButtonStyle())
            }
            partRow("wake", wake.paused ? "Weckwort fortsetzen" : "Weckwort pausieren",
                    symbol: wake.paused ? "ear" : "pause.circle", hotkey: nil, note: wakeNote) {
                wake.togglePause()
            }
            if model.part("notaus") {
                Button {
                    go { model.confirmNotaus() }
                } label: {
                    HStack(spacing: 10) {
                        IconTile(symbol: "octagon", color: Theme.bad)
                        Text(verbatim: "Mein Notaus …")
                            .font(.system(size: 13))
                            .foregroundColor(Theme.bad)
                        Spacer()
                    }
                }
                .buttonStyle(RowButtonStyle())
            }
        }
    }

    // ------------------------------------------------------------------ Version 4 sections

    private func sectionTitle(_ t: String) -> some View {
        Text(verbatim: t)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(Theme.muted)
            .padding(.horizontal, 10)
    }

    /// "Als Nächstes": the next events and reminders (part agenda)
    private var agendaSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionTitle("Als Nächstes")
            let now = Date()
            let lines = agenda.agenda.upcoming(now: now)
            if !agenda.problem.isEmpty && lines.isEmpty {
                Text(verbatim: agenda.problem)
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 10)
                    .fixedSize(horizontal: false, vertical: true)
            } else if lines.isEmpty {
                Text(verbatim: agenda.loaded ? "Nichts in den nächsten 24 Stunden." : "Lädt …")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 10)
            } else {
                ForEach(lines) { l in
                    HStack(alignment: .top, spacing: 10) {
                        IconTile(symbol: l.isReminder ? "bell" : "calendar")
                        VStack(alignment: .leading, spacing: 1) {
                            Text(verbatim: l.title)
                                .font(.system(size: 13))
                                .lineLimit(2)
                            Text(verbatim: IsoDate.short(l.when, now: now) + (l.detail.isEmpty ? "" : " · " + l.detail))
                                .font(.system(size: 11))
                                .foregroundColor(Theme.muted)
                                .lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 3)
                }
            }
        }
    }

    /// "Zuhause": the Smart-Home buttons with their state (part home); the panel stays open
    private var homeSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionTitle("Zuhause")
            if home.buttons.isEmpty {
                Text(Wege.text(home.problem.isEmpty ? "Keine Knöpfe – im Panel unter Ich → Begleiter festlegen." : home.problem))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 10)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                FlowLayout(spacing: 6) {
                    ForEach(home.buttons) { b in
                        homeButton(b)
                    }
                }
                .padding(.horizontal, 10)
                if !home.problem.isEmpty {
                    Text(verbatim: home.problem)
                        .font(.system(size: 11))
                        .foregroundColor(Theme.bad)
                        .padding(.horizontal, 10)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func homeButton(_ b: HomeButton) -> some View {
        let on = b.state == "on"
        let symbol: String
        switch b.kind {
        case "scene": symbol = "sparkles"
        case "script": symbol = "play.fill"
        default: symbol = on ? "lightbulb.fill" : "lightbulb"
        }
        return Button {
            home.press(b)
        } label: {
            HStack(spacing: 6) {
                if home.pressing == b.id {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: symbol)
                        .font(.system(size: 11, weight: .medium))
                }
                Text(verbatim: b.name)
                    .font(.system(size: 12))
                    .lineLimit(1)
                if b.kind == "toggle", let st = b.state {
                    Text(verbatim: st == "on" ? "an" : "aus")
                        .font(.system(size: 10, weight: .semibold))
                        .opacity(0.8)
                }
            }
            .foregroundColor(on ? .white : Theme.fg)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Capsule().fill(on ? Theme.accent : Theme.soft))
            .overlay(Capsule().stroke(on ? Theme.accent : Theme.line, lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(home.pressing != nil)
        .accessibilityLabel(Text(verbatim: b.name + (b.state.map { $0 == "on" ? ", an" : ", aus" } ?? "")))
    }

    private var wakeNote: String {
        if mic.closed { return "Mikrofon zu" }
        if !wake.problem.isEmpty { return wake.problem }
        if wake.paused { return "pausiert" }
        if wake.question { return "hört deine Frage …" }
        return wake.listening ? "hört auf „\(wake.word)“" : "startet …"
    }

    @ViewBuilder
    private func partRow(_ part: String, _ title: String, symbol: String, hotkey: HotAction?, note: String = "",
                         run: @escaping () -> Void) -> some View {
        if model.part(part) {
            Button {
                go(run)
            } label: {
                HStack(spacing: 10) {
                    IconTile(symbol: symbol)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(verbatim: title)
                            .font(.system(size: 13))
                        if !note.isEmpty {
                            Text(Wege.text(note))
                                .font(.system(size: 11))
                                .foregroundColor(Theme.muted)
                                .lineLimit(2)
                        }
                    }
                    Spacer()
                    let key = hotkey.map { model.hotkeyLabel($0) } ?? ""
                    if !key.isEmpty { KeyChip(text: key) }
                }
            }
            .buttonStyle(RowButtonStyle())
        } else if model.allowedPart(part) {
            HStack(spacing: 10) {
                IconTile(symbol: symbol, color: Theme.muted)
                VStack(alignment: .leading, spacing: 1) {
                    Text(verbatim: title)
                        .font(.system(size: 13))
                        .foregroundColor(Theme.muted)
                    Text(Wege.text("Im Panel unter Ich → Begleiter einschalten"))
                        .font(.system(size: 11))
                        .foregroundColor(Theme.muted)
                }
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
    }

    private var footer: some View {
        VStack(spacing: 10) {
            Rectangle().fill(Theme.line).frame(height: 1)
            // Labels never break inside a word: if the panel is too narrow, the coffee pill goes to its own line.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) {
                    footerButtons
                    Spacer(minLength: 4)
                    CoffeePill(title: "Spark unterstützen", url: model.coffee)
                }
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) { footerButtons }
                    CoffeePill(title: "Spark unterstützen", url: model.coffee)
                }
            }
        }
    }

    @ViewBuilder private var footerButtons: some View {
        Button("Einstellungen") { go { Windows.showSettings() } }
            .buttonStyle(SoftButtonStyle())
        Button("Panel öffnen") { go { model.openPanel() } }
            .buttonStyle(SoftButtonStyle())
            .disabled(model.base == nil)
    }

    /// closes the panel, then runs the action (an alert or another window must not fight with the panel)
    private func go(_ f: @escaping () -> Void) {
        holder.close()
        DispatchQueue.main.async { f() }
    }
}

/// "Neue Version 1.0.350 · Geprüft vom Spark · 64 MB" + "Aktualisieren"
struct UpdateBanner: View {
    let info: UpdateInfo
    @ObservedObject var updater: Updater

    var body: some View {
        HStack(spacing: 10) {
            IconTile(symbol: "arrow.down.to.line", back: Theme.card)
            VStack(alignment: .leading, spacing: 1) {
                Text(verbatim: "Neue Version \(info.version)")
                    .font(.system(size: 12, weight: .semibold))
                Text(verbatim: line)
                    .font(.system(size: 11))
                    .foregroundColor(isFailed ? Theme.bad : Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 4)
            if busy {
                ProgressView().controlSize(.small)
            }
            Button(isFailed ? "Nochmal" : "Aktualisieren") { updater.install() }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 10).fill(Theme.card)
                .overlay(RoundedRectangle(cornerRadius: 10).fill(Theme.accent.opacity(0.10)))
        )
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.accent.opacity(0.35), lineWidth: 1))
    }

    private var busy: Bool {
        updater.phase == .downloading || updater.phase == .installing
    }

    private var isFailed: Bool {
        if case .failed = updater.phase { return true }
        return false
    }

    private var line: String {
        switch updater.phase {
        case .downloading: return "Lädt vom Spark … · \(info.sizeText)"
        case .ready: return "Geladen und geprüft · \(info.sizeText)"
        case .installing: return "Wird installiert, der Begleiter startet neu …"
        case .failed(let m): return m
        default: return "Geprüft vom Spark · \(info.sizeText)"
        }
    }
}
