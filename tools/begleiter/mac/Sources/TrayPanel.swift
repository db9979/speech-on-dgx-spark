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

/// Click on the face in the menu bar ("Begleiter aufpolieren" 1a, Dominik 2026-10-17): gradient bar, face with greeting
/// and state, settings and quit; the update banner; the field "Frag Spark …"; the commands as tiles; then sections
/// like in the panel (Als Nächstes, Zuhause, Dieser Mac with switches); at the bottom "Panel öffnen" and Notaus.
/// The coffee is only in Einstellungen → Über und Update. Closes on focus loss and Esc.
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
    @ObservedObject var lists = ListsCenter.shared
    @ObservedObject var post = PostCenter.shared
    @ObservedObject var home = HomeCenter.shared
    @State private var holder = PanelWindow()

    private static let tileColumns = [GridItem(.flexible(), spacing: 7), GridItem(.flexible(), spacing: 7),
                                      GridItem(.flexible(), spacing: 7)]

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 10) {
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
                    if model.part("ask") {
                        PanelAskField(key: model.hotkeyLabel(.ask),
                                      voice: model.part("dictate") && !mic.closed,
                                      submit: { q in go { model.askFromPanel(q) } },
                                      speak: { go { model.askByVoice() } })
                    }
                    tiles
                    if model.part("post") { postSection }
                    if model.part("agenda") { agendaSection }
                    if model.part("lists") { listsSection }
                    if model.part("home") { homeSection }
                    thisMac
                    if !moreHint.isEmpty {
                        Text(Wege.text(moreHint))
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                            .padding(.horizontal, 2)
                    }
                } else {
                    PanelBox {
                        PanelRow(title: "Mit dem Spark koppeln", detail: "Einmal verbinden, dann geht alles hier.",
                                 symbol: "link", verb: "Koppeln …") { go { Windows.showPairing() } }
                    }
                }
            }
            .padding(14)
            footer
        }
        .frame(width: 360)
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .background(WindowGrabber { w in holder.window = w })
        .onExitCommand { holder.close() }
        .onAppear {
            agenda.refreshSoon()
            post.refreshSoon()
            lists.refreshSoon()
            home.refreshSoon()
        }
    }

    // ------------------------------------------------------------------ parts of the panel

    /// "Guten Morgen, Dominik" (or the program's name before pairing)
    private var greeting: String {
        let p = model.config?.profile ?? ""
        guard model.paired, !p.isEmpty else { return "Spark-Begleiter" }
        return Self.greeting(hour: Calendar.current.component(.hour, from: Date())) + ", " + p
    }

    static func greeting(hour: Int) -> String {
        switch hour {
        case 5..<11: return "Guten Morgen"
        case 18..<23: return "Guten Abend"
        default: return "Hallo"
        }
    }

    /// the reason when the Spark is not reachable or a Notaus holds
    private var detail: String {
        guard model.paired, model.reach == .offline || model.reach == .notaus else { return "" }
        return model.reachText
    }

    private var stateLine: String {
        let pill = model.reachPill
        let text = model.reach == .ok && model.paired ? "alles läuft" : pill.text
        return model.paired ? model.deviceName + " · " + text : text
    }

    private var header: some View {
        HStack(spacing: 11) {
            FaceView(size: 40)
            VStack(alignment: .leading, spacing: 1) {
                Text(verbatim: greeting)
                    .font(.system(size: 14, weight: .semibold))
                    .lineLimit(1)
                HStack(spacing: 6) {
                    Circle().fill(model.reachPill.color).frame(width: 7, height: 7)
                    Text(verbatim: stateLine)
                        .font(.system(size: 12))
                        .foregroundColor(model.reach == .notaus ? Theme.bad : Theme.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            .frame(minWidth: 0)
            Spacer(minLength: 4)
            headerIcon("gearshape", "Einstellungen") { go { Windows.showSettings() } }
            headerIcon("power", "Spark-Begleiter beenden") { NSApp.terminate(nil) }
        }
    }

    private func headerIcon(_ symbol: String, _ label: String, run: @escaping () -> Void) -> some View {
        Button(action: run) {
            Image(systemName: symbol)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Theme.muted)
                .frame(width: 26, height: 26)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(Text(verbatim: label))
        .accessibilityLabel(Text(verbatim: label))
    }

    /// the commands as tiles, three in a row (only the parts that are on)
    private var tiles: some View {
        LazyVGrid(columns: Self.tileColumns, alignment: .leading, spacing: 7) {
            if model.part("write") {
                PanelTile(title: "Text verbessern", symbol: "pencil", color: Theme.accent, key: model.hotkeyLabel(.write)) {
                    go { Task { await model.startWrite(fromMenu: true) } }
                }
            }
            if model.part("dictate") {
                PanelTile(title: dictation.recording ? "Diktat beenden" : "Diktieren",
                          symbol: dictation.recording ? "stop.circle" : "mic", color: Theme.accent2,
                          key: model.hotkeyLabel(.dictate), danger: dictation.recording) {
                    go { dictation.toggle(.cursor(nil)) }
                }
            }
            if model.part("screen") {
                PanelTile(title: "Bildschirm fragen", symbol: "viewfinder", color: Theme.accent, key: model.hotkeyLabel(.screen)) {
                    go { ScreenAsk.start() }
                }
            }
            if model.part("mail") {
                PanelTile(title: "Antwort entwerfen", symbol: "envelope", color: Theme.accent2, key: model.hotkeyLabel(.mail)) {
                    go { MailDraft.start(front: nil) }
                }
            }
            if model.part("speak") {
                PanelTile(title: speaker.active ? "Vorlesen stoppen" : "Vorlesen",
                          symbol: speaker.active ? "stop.circle" : "speaker.wave.2", color: Theme.ok,
                          key: model.hotkeyLabel(.speak)) {
                    go { if speaker.active { speaker.stop() } else { speaker.readClipboard() } }
                }
            }
            if model.part("capture") {
                PanelTile(title: "Erfassen", symbol: "plus.circle", color: Theme.accent2, key: model.hotkeyLabel(.capture)) {
                    go { CaptureController.open(fromHotkey: false) }
                }
            }
            if model.part("meeting") {
                PanelTile(title: meeting.running ? "Mitschreiben beenden" : "Mitschreiben",
                          symbol: meeting.running ? "stop.circle" : "record.circle", color: Theme.bad,
                          key: model.hotkeyLabel(.meeting), danger: meeting.running) {
                    go { meeting.toggle() }
                }
            }
        }
    }

    /// "Dieser Mac": switches (microphone, wake word) and rows with a word on the right; switches keep the panel open
    @ViewBuilder
    private var thisMac: some View {
        let rows = macRows
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                SectionLabel(text: "Dieser Mac")
                PanelBox {
                    ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                        if i > 0 { RowLine() }
                        row
                    }
                }
            }
        }
    }

    private var macRows: [AnyView] {
        var rows: [AnyView] = []
        if model.usesMic {
            rows.append(AnyView(PanelRow(title: "Mikrofon", detail: mic.closed ? "Zu: nichts hört mit." : "Offen für Diktat, Fragen und Weckwort.",
                                         symbol: mic.closed ? "mic.slash" : "mic", on: !mic.closed) { mic.toggle() }))
        }
        if model.part("wake") {
            rows.append(AnyView(PanelRow(title: "Weckwort „\(wake.word)“", detail: wakeNote, symbol: "waveform",
                                         on: !wake.paused && !mic.closed) { wake.togglePause() }
                .disabled(mic.closed)))
        }
        if model.part("act") {
            rows.append(AnyView(PanelRow(title: "Am Mac handeln", detail: "Ohne Rückfrage, Kurzbefehle",
                                         symbol: "hand.tap", verb: "Einstellen") { go { ActSettings.show() } }))
        }
        if model.part("folder") {
            rows.append(AnyView(PanelRow(title: "Wissen-Ordner",
                                         detail: folder.lastText.isEmpty ? folder.path.lastPathComponent : folder.lastText,
                                         symbol: "folder", verb: "Öffnen") { go { folder.reveal() } }))
        }
        if model.part("inbox") {
            rows.append(AnyView(PanelRow(title: "Vom Spark", detail: "Vom Handy · Downloads/\(InboxCenter.folderName)",
                                         symbol: "tray.and.arrow.down", verb: "Öffnen") { go { InboxCenter.revealFolder() } }))
        }
        if model.part("quiet") {
            rows.append(AnyView(PanelRow(title: "Nicht stören erkennen", detail: quiet.text,
                                         symbol: quiet.busy ? "moon.fill" : "moon", verb: "Prüfen") { quiet.check() }))
        }
        if model.part("office") {
            rows.append(AnyView(PanelRow(title: "Office-Add-ins", detail: "Schreibhilfe in Word, Excel und Outlook.",
                                         symbol: "square.grid.2x2", verb: "Einrichten") { go { OfficeSetup.start(model: model) } }))
        }
        return rows
    }

    /// parts the admin released that are still off on this device
    private var moreHint: String {
        guard let cfg = model.config else { return "" }
        let off = DeskConfig.partNames.contains { cfg.parts[$0] != true && cfg.allowed[$0] == true }
        return off ? "Weitere Teile im Panel unter Ich → Begleiter." : ""
    }

    // ------------------------------------------------------------------ Version 4 sections

    private func sectionTitle(_ t: String) -> some View {
        SectionLabel(text: t)
    }

    /// "Post": unread mail and Für dich as numbers, the urgent cards with their buttons (part post)
    private var postSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionTitle("Post")
            PanelBox {
                PanelRow(title: post.loaded ? post.post.summary : "Lädt …",
                         detail: !post.problem.isEmpty ? post.problem : post.post.loading ? "Wird noch gelesen …" : "",
                         symbol: "envelope", verb: post.post.noMail ? "" : "E-Mail öffnen") {
                    go { model.openPanel("#me=mailbox") }
                }
                ForEach(post.post.cards) { c in
                    RowLine()
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: c.title)
                            .font(.system(size: 13, weight: .semibold))
                            .lineLimit(2)
                        if !c.line.isEmpty {
                            Text(verbatim: c.line)
                                .font(.system(size: 11))
                                .foregroundColor(Theme.muted)
                                .lineLimit(2)
                        }
                        HStack(spacing: 6) {
                            ForEach(c.acts, id: \.self) { a in
                                Button(NoteActions.panelLabel(a) ?? a) { post.act(c, a) }
                                    .buttonStyle(SoftButtonStyle())
                            }
                            Button("Ansehen") {
                                go {
                                    if let url = Wege.link("E-Mail → Für dich", base: model.base) { NSWorkspace.shared.open(url) }
                                }
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                }
            }
        }
    }

    /// "Listen": the lists with open entries (part lists); a row opens the page Listen
    private var listsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionTitle("Listen")
            PanelBox {
                if lists.rows.isEmpty {
                    PanelRow(title: !lists.problem.isEmpty ? lists.problem : lists.loaded ? "Keine Listen." : "Lädt …",
                             detail: "", symbol: "list.bullet", verb: "Öffnen") { go { model.openPanel("#me=taskbox") } }
                }
                ForEach(Array(lists.rows.enumerated()), id: \.element.id) { i, l in
                    if i > 0 { RowLine() }
                    PanelRow(title: (l.icon.isEmpty ? "" : l.icon + " ") + l.name, detail: l.detail,
                             symbol: "list.bullet", verb: "Öffnen") { go { model.openPanel("#me=taskbox") } }
                }
            }
        }
    }

    /// "Als Nächstes": the next events and reminders (part agenda), in a box like in the panel
    private var agendaSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionTitle("Als Nächstes")
            let now = Date()
            let lines = agenda.agenda.upcoming(now: now)
            if !agenda.problem.isEmpty && lines.isEmpty {
                Text(verbatim: agenda.problem)
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 2)
                    .fixedSize(horizontal: false, vertical: true)
            } else if lines.isEmpty {
                Text(verbatim: agenda.loaded ? "Nichts in den nächsten 24 Stunden." : "Lädt …")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 2)
            } else {
                PanelBox {
                    ForEach(Array(lines.enumerated()), id: \.element.id) { i, l in
                        if i > 0 { RowLine() }
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: l.isReminder ? "bell" : "calendar")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Theme.accent)
                                .frame(width: 20)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(verbatim: l.title)
                                    .font(.system(size: 13))
                                    .lineLimit(2)
                                HStack(spacing: 5) {
                                    if !l.who.isEmpty {
                                        // whose shared calendar (Begleiter nachziehen 7a)
                                        Text(verbatim: l.who)
                                            .font(.system(size: 10, weight: .semibold))
                                            .foregroundColor(Theme.accent)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 1)
                                            .background(Capsule().fill(Theme.accent.opacity(0.12)))
                                            .lineLimit(1)
                                    }
                                    Text(verbatim: IsoDate.short(l.when, now: now) + (l.detail.isEmpty ? "" : " · " + l.detail))
                                        .font(.system(size: 11))
                                        .foregroundColor(Theme.muted)
                                        .lineLimit(1)
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .contentShape(Rectangle())
                        .onTapGesture { if !l.day.isEmpty { model.openPanel("#kal=" + l.day) } }
                        .help(Text(verbatim: l.day.isEmpty ? "" : "Im Kalender öffnen"))
                    }
                }
            }
        }
    }

    /// "Zuhause": the Smart-Home buttons with their state (part home); the panel stays open
    private var homeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionTitle("Zuhause")
            if home.buttons.isEmpty {
                Text(Wege.text(home.problem.isEmpty ? "Keine Knöpfe – im Panel unter Ich → Begleiter festlegen." : home.problem))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 2)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                FlowLayout(spacing: 6) {
                    ForEach(home.buttons) { b in
                        homeButton(b)
                    }
                }
                if !home.problem.isEmpty {
                    Text(verbatim: home.problem)
                        .font(.system(size: 11))
                        .foregroundColor(Theme.bad)
                        .padding(.horizontal, 2)
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

    /// the foot on the soft surface: "Panel öffnen" on the left, Notaus in red on the right
    private var footer: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Theme.line).frame(height: 1)
            HStack(spacing: 8) {
                Button {
                    go { model.openPanel() }
                } label: {
                    Label { Text(verbatim: "Panel öffnen") } icon: { Image(systemName: "arrow.up.right.square") }
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.accent)
                        .lineLimit(1)
                        .fixedSize()
                }
                .buttonStyle(.plain)
                .disabled(model.base == nil)
                Spacer(minLength: 4)
                if model.paired && model.part("notaus") {
                    Button {
                        go { model.confirmNotaus() }
                    } label: {
                        Label { Text(verbatim: "Notaus …") } icon: { Image(systemName: "exclamationmark.octagon") }
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(Theme.bad)
                        .lineLimit(1)
                        .fixedSize()
                    }
                    .buttonStyle(.plain)
                    .help(Text(verbatim: "Mein Notaus auslösen (mit Rückfrage)"))
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Theme.soft)
        }
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

/// The field "Frag Spark …" at the top of the tray panel; its text lives here, not in the panel's state (typing comes
/// first). Return asks, the microphone opens Frag Spark listening.
struct PanelAskField: View {
    let key: String
    let voice: Bool
    let submit: (String) -> Void
    let speak: () -> Void
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 8) {
            TextField(text: $text, prompt: Text(verbatim: "Frag Spark …")) { Text(verbatim: "Frag Spark") }
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .focused($focused)
                .onSubmit { submit(text.trimmingCharacters(in: .whitespacesAndNewlines)) }
            if !key.isEmpty && text.isEmpty {
                Text(verbatim: key)
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
            }
            if voice {
                Button(action: speak) {
                    Image(systemName: "mic")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: 26, height: 26)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.diagonal))
                        .contentShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .help(Text(verbatim: "Frage sprechen"))
                .accessibilityLabel(Text(verbatim: "Frag Spark: sprechen"))
            }
        }
        .padding(.leading, 11)
        .padding(.trailing, 6)
        .padding(.vertical, 6)
        .frame(minHeight: 38)
        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.soft))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(focused ? Theme.accent : Theme.line, lineWidth: focused ? 1.5 : 1))
        .onAppear { DispatchQueue.main.async { focused = true } }
    }
}
