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
    /// the panel's own height, measured; the window follows it
    var height: CGFloat = 0

    @MainActor
    func close() {
        window?.close()
    }

    /// The window exactly as high as the panel, its top edge stays under the menu bar (Dominik 2026-10-24: the
    /// MenuBarExtra window grows with the content but never shrinks back; the panel then sat in the middle of a
    /// too-high window, with empty room above and below).
    @MainActor
    func fit() {
        guard let w = window, height > 0 else { return }
        let content = w.contentRect(forFrameRect: w.frame).height
        guard abs(content - height) > 0.5 else { return }
        var f = w.frame
        let top = f.maxY
        f.size.height = w.frameRect(forContentRect: NSRect(x: 0, y: 0, width: f.width, height: height)).height
        f.origin.y = top - f.size.height
        w.setFrame(f, display: true, animate: false)
    }
}

/// The tabs below the tiles ("Begleiter-Fenster ordnen" 1a, Dominik 2026-10-21); only the tab scrolls.
enum PanelTab: String, CaseIterable {
    case heute = "Heute"
    case meldungen = "Meldungen"
    case rechner = "Rechner"
}

/// The height of a part of the panel, measured, so the tab gets exactly the room it needs (up to the screen).
private struct PanelHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

private struct RootHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

private struct FixedHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// Click on the face in the menu bar ("Begleiter aufpolieren" 1a, Dominik 2026-10-17): gradient bar, face with greeting
/// and state, settings and quit; the update banner; the field "Frag Spark …"; the commands as small tiles. Below three
/// tabs ("Begleiter-Fenster ordnen", Dominik 2026-10-21): "Heute" (Als Nächstes, Post, Listen), "Meldungen" and
/// "Rechner" (Zuhause, Dieser Mac); only the tab scrolls and the panel is at most as high as the free screen. At the
/// bottom "Panel öffnen" and Notaus. The coffee is only in Einstellungen → Über und Update. Closes on focus loss and Esc.
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
    @ObservedObject var offen = OffenCenter.shared
    @ObservedObject var post = PostCenter.shared
    @ObservedObject var home = HomeCenter.shared
    @ObservedObject var notes = NotesCenter.shared
    @State private var holder = PanelWindow()
    /// the tab open last, on this Mac only (6a)
    @AppStorage("panelTab") private var savedTab = PanelTab.heute.rawValue
    @State private var tab: PanelTab?
    @State private var agendaAll = false
    @State private var postAll = false
    @State private var tabHeight: CGFloat = 0
    @State private var measured: CGFloat = 0
    @State private var fixedHeight: CGFloat = 0

    /// four small tiles in a row (3a)
    private static let tileColumns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 4)
    /// the first three of a section, below "Alle n zeigen" (4a)
    private static let firstShown = 3

    var body: some View {
        VStack(spacing: 0) {
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
                    if openTabs.count > 1 { tabPicker }
                } else {
                    PanelBox {
                        PanelRow(title: "Mit dem Spark koppeln", detail: "Einmal verbinden, dann geht alles hier.",
                                 symbol: "link", verb: "Koppeln …") { go { Windows.showPairing() } }
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.top, 14)
            .padding(.bottom, showsTab ? 4 : 14)
            .background(GeometryReader { g in Color.clear.preference(key: FixedHeightKey.self, value: g.size.height) })
            if showsTab {
                // only the tab scrolls, with one bar; at most as high as the free screen (2a)
                ScrollView(.vertical) {
                    VStack(alignment: .leading, spacing: 10) {
                        tabContent
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(GeometryReader { g in Color.clear.preference(key: PanelHeightKey.self, value: g.size.height) })
                }
                .frame(height: min(max(tabHeight, 40), maxTabHeight))
            }
            if model.paired && !moreHint.isEmpty {
                Text(Wege.text(moreHint))
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 10)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            footer
        }
        .frame(width: 360)
        .fixedSize(horizontal: false, vertical: true)
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .background(GeometryReader { g in Color.clear.preference(key: RootHeightKey.self, value: g.size.height) })
        .onPreferenceChange(RootHeightKey.self) { h in
            holder.height = h
            holder.fit()
        }
        .background(WindowGrabber { w in
            holder.window = w
            holder.fit()
        })
        .onExitCommand { holder.close() }
        .onPreferenceChange(PanelHeightKey.self) { h in
            // grows with the tab, never shrinks while open: switching tabs does not make the panel jump
            measured = h
            if h > tabHeight { tabHeight = h }
        }
        .onPreferenceChange(FixedHeightKey.self) { h in fixedHeight = h }
        .onAppear {
            // a note not shown yet: open on "Meldungen" (5a), else the tab open last (6a)
            tab = notes.unseen ? .meldungen : (PanelTab(rawValue: savedTab) ?? .heute)
            notes.markSeen()
            tabHeight = measured
            agendaAll = false
            postAll = false
            agenda.refreshSoon()
            post.refreshSoon()
            lists.refreshSoon()
            offen.refreshSoon()
            home.refreshSoon()
        }
        .onChange(of: notes.items.first?.n) { _ in
            // a new note while the panel is open: show it at once
            if notes.unseen {
                tab = .meldungen
                notes.markSeen()
            }
        }
    }

    // ------------------------------------------------------------------ tabs

    private var showsTab: Bool { model.paired && !openTabs.isEmpty }

    /// the room for the tab: the free screen (menu bar and Dock left out) minus the fixed parts, at least 160
    private var maxTabHeight: CGFloat {
        let screen = holder.window?.screen?.visibleFrame.height ?? NSScreen.main?.visibleFrame.height ?? 800
        return max(160, screen - fixedHeight - 70 - (moreHint.isEmpty ? 0 : 30))
    }

    /// only tabs with something to show; no bar when only one is left
    private var openTabs: [PanelTab] {
        PanelTab.allCases.filter { t in
            switch t {
            case .heute: return model.part("agenda") || model.part("post") || model.part("lists") || model.part("offen")
            case .meldungen: return model.part("notes")
            case .rechner: return model.part("home") || !macRows.isEmpty
            }
        }
    }

    private var current: PanelTab {
        let t = tab ?? .heute
        return openTabs.contains(t) ? t : (openTabs.first ?? .heute)
    }

    private func tabLabel(_ t: PanelTab) -> String {
        t == .meldungen && !notes.items.isEmpty ? "Meldungen \(notes.items.count)" : t.rawValue
    }

    private var tabPicker: some View {
        Picker(selection: Binding(get: { current }, set: { t in
            tab = t
            savedTab = t.rawValue
        })) {
            ForEach(openTabs, id: \.self) { t in
                Text(verbatim: tabLabel(t)).tag(t)
            }
        } label: {
            Text(verbatim: "Reiter")
        }
        .pickerStyle(.segmented)
        .labelsHidden()
    }

    @ViewBuilder
    private var tabContent: some View {
        switch current {
        case .heute:
            if model.part("agenda") { agendaSection }
            if model.part("post") { postSection }
            if model.part("lists") { listsSection }
            if model.part("offen") { offenSection }
        case .meldungen:
            notesSection
        case .rechner:
            if model.part("home") { homeSection }
            thisMac
        }
    }

    /// "Alle n zeigen" / "Weniger zeigen" below a shortened section (4a); the panel stays open
    private func moreButton(count: Int, all: Bool, toggle: @escaping () -> Void) -> some View {
        Button(action: toggle) {
            Text(verbatim: all ? "Weniger zeigen" : "Alle \(count) zeigen")
                .font(.system(size: 11.5, weight: .semibold))
                .foregroundColor(Theme.accent)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 2)
    }

    /// "Meldungen": the Spark's notes of this run, newest first, with their buttons; "OK" only takes one away (5a)
    private var notesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if openTabs.count < 2 { SectionLabel(text: "Meldungen", count: notes.items.count) }
            if notes.items.isEmpty {
                Text(verbatim: "Keine Meldungen.")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .padding(.horizontal, 2)
            }
            ForEach(notes.items) { n in
                PanelBox {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: n.title)
                            .font(.system(size: 13, weight: .semibold))
                            .lineLimit(2)
                        if !n.body.isEmpty {
                            Text(verbatim: n.body)
                                .font(.system(size: 11))
                                .foregroundColor(Theme.muted)
                                .lineLimit(2)
                        }
                        FlowLayout(spacing: 6) {
                            Button("OK") { notes.dismiss(n) }
                                .buttonStyle(SoftButtonStyle())
                            ForEach(n.buttons, id: \.self) { a in
                                Button(NotesCenter.label(a, n)) { go { notes.run(a, n) } }
                                    .buttonStyle(SoftButtonStyle())
                            }
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
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
        let text = model.reach == .ok && model.paired ? (model.reachText.isEmpty ? "alles läuft" : model.reachText) : pill.text
        return model.paired ? model.deviceName + " · " + text : text
    }

    private var header: some View {
        HStack(spacing: 11) {
            if FacePref.on { FaceView(size: 40) }
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

    /// the commands as small tiles, four in a row (only the parts that are on; the hotkey is in the help)
    private var tiles: some View {
        LazyVGrid(columns: Self.tileColumns, alignment: .leading, spacing: 6) {
            if model.part("write") {
                PanelTile(title: "Text verbessern", symbol: "pencil", color: Theme.accent, key: model.hotkeyLabel(.write), compact: true) {
                    go { Task { await model.startWrite(fromMenu: true) } }
                }
            }
            if model.part("dictate") {
                PanelTile(title: dictation.recording ? "Diktat beenden" : "Diktieren",
                          symbol: dictation.recording ? "stop.circle" : "mic", color: Theme.accent,
                          key: model.hotkeyLabel(.dictate), danger: dictation.recording, compact: true) {
                    go { dictation.toggle(.cursor(nil)) }
                }
            }
            if model.part("screen") {
                PanelTile(title: "Bildschirm fragen", symbol: "viewfinder", color: Theme.accent, key: model.hotkeyLabel(.screen), compact: true) {
                    go { ScreenAsk.start() }
                }
            }
            if model.part("mail") {
                PanelTile(title: "Antwort entwerfen", symbol: "envelope", color: Theme.accent, key: model.hotkeyLabel(.mail), compact: true) {
                    go { MailDraft.start(front: nil) }
                }
            }
            if model.part("speak") {
                PanelTile(title: speaker.active ? "Vorlesen stoppen" : "Vorlesen",
                          symbol: speaker.active ? "stop.circle" : "speaker.wave.2", color: Theme.ok,
                          key: model.hotkeyLabel(.speak), compact: true) {
                    go { if speaker.active { speaker.stop() } else { speaker.readClipboard() } }
                }
            }
            if model.part("capture") {
                PanelTile(title: "Erfassen", symbol: "plus.circle", color: Theme.accent, key: model.hotkeyLabel(.capture), compact: true) {
                    go { CaptureController.open(fromHotkey: false) }
                }
            }
            if model.part("find") {
                PanelTile(title: "Finden", symbol: "magnifyingglass", color: Theme.accent, key: model.hotkeyLabel(.find), compact: true) {
                    go { FindController.open(fromHotkey: false) }
                }
            }
            if model.part("meeting") {
                PanelTile(title: meeting.running ? "Mitschreiben beenden" : "Mitschreiben",
                          symbol: meeting.running ? "stop.circle" : "record.circle", color: Theme.bad,
                          key: model.hotkeyLabel(.meeting), danger: meeting.running, compact: true) {
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
                ForEach(postAll ? post.post.cards : Array(post.post.cards.prefix(Self.firstShown - 1))) { c in
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
            if post.post.cards.count + 1 > Self.firstShown {
                moreButton(count: post.post.cards.count + 1, all: postAll) { postAll.toggle() }
            }
        }
    }

    /// "Listen": one line per list (name, open entries, the last one; part lists); a row opens the page Listen
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
                    PanelRow(title: (l.icon.isEmpty ? "" : l.icon + " ") + l.name + " · " + l.detail,
                             symbol: "list.bullet", verb: "Öffnen") { go { model.openPanel("#me=taskbox") } }
                        .help(Text(verbatim: l.name + " · " + l.detail))
                }
            }
        }
    }

    /// "Offen": how many Vorgänge wait, the first three cards with their fixed buttons (part offen); a card without a
    /// button opens Offen in the panel
    private var offenSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionTitle(offen.n > 0 ? "Offen \(offen.n)" : "Offen")
            PanelBox {
                if offen.cards.isEmpty {
                    PanelRow(title: !offen.problem.isEmpty ? offen.problem : offen.loaded ? "Nichts offen." : "Lädt …",
                             detail: "", symbol: "tray", verb: "Öffnen") { go { model.openPanel("#me=vgbox") } }
                }
                ForEach(Array(offen.cards.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { RowLine() }
                    VStack(alignment: .leading, spacing: 4) {
                        PanelRow(title: c.titel.isEmpty ? c.art : c.titel,
                                 detail: [c.art, c.zeile].filter { !$0.isEmpty }.joined(separator: " · "),
                                 symbol: "tray", verb: c.acts.isEmpty ? "Öffnen" : "") { go { model.openPanel("#me=vgbox") } }
                        if !c.acts.isEmpty {
                            HStack(spacing: 6) {
                                ForEach(c.acts, id: \.k) { a in
                                    Button(a.de) { offen.act(c, a.k) }
                                        .buttonStyle(SoftButtonStyle())
                                        .disabled(offen.busy)
                                }
                            }
                            .padding(.leading, 30)
                            .padding(.bottom, 4)
                        }
                    }
                }
                if offen.n > offen.cards.count {
                    RowLine()
                    PanelRow(title: "Alle \(offen.n) ansehen", symbol: "arrow.up.right.square", verb: "Öffnen") {
                        go { model.openPanel("#me=vgbox") }
                    }
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
            let shown = agendaAll ? lines : Array(lines.prefix(Self.firstShown))
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
                    ForEach(Array(shown.enumerated()), id: \.element.id) { i, l in
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
                if lines.count > Self.firstShown {
                    moreButton(count: lines.count, all: agendaAll) { agendaAll.toggle() }
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
            .foregroundColor(on ? Theme.onAccent : Theme.fg)
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
                        .foregroundColor(Theme.onAccent)
                        .frame(width: 26, height: 26)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.accent))
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
