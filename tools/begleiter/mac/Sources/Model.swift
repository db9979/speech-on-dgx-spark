import AppKit
import ServiceManagement
import SwiftUI
import UserNotifications

struct ArtInfo: Identifiable, Equatable {
    let id: String
    let de: String
    let changes: Bool
}

struct LangInfo: Identifiable, Equatable {
    let id: String
    let de: String
}

/// GET /api/desk/config, every value checked; anything missing or odd falls back to a safe default.
struct DeskConfig: Equatable {
    static let partNames = ["write", "ask", "dictate", "notes", "status", "notaus",
                            "files", "screen", "context", "mail", "folder", "actions", "act", "wake",
                            "speak", "inbox", "agenda", "quiet", "meeting", "home", "daily", "office", "view", "post", "capture", "lists"]
    static let fallbackArts = [
        ArtInfo(id: "korrigieren", de: "Korrigieren", changes: true),
        ArtInfo(id: "glaetten", de: "Glätten", changes: true),
        ArtInfo(id: "kuerzer", de: "Kürzer", changes: true),
        ArtInfo(id: "freundlicher", de: "Freundlicher", changes: true),
        ArtInfo(id: "foermlicher", de: "Förmlicher", changes: true),
        ArtInfo(id: "uebersetzen", de: "Übersetzen", changes: false),
    ]
    static let fallbackLangs = [
        LangInfo(id: "de", de: "Deutsch"), LangInfo(id: "en", de: "Englisch"), LangInfo(id: "fr", de: "Französisch"),
        LangInfo(id: "es", de: "Spanisch"), LangInfo(id: "it", de: "Italienisch"), LangInfo(id: "nl", de: "Niederländisch"),
    ]

    var rev = 0
    var profile = ""
    var parts: [String: Bool] = [:]
    var allowed: [String: Bool] = [:]
    var writeArt = "korrigieren"
    var writeSprache = "en"
    var writeWunsch = ""
    var writeArts: [String] = ["korrigieren"]
    var preview = true
    var dictateSprache = "auto"
    var autostart: Bool?
    var arts: [ArtInfo] = DeskConfig.fallbackArts
    var langs: [LangInfo] = DeskConfig.fallbackLangs
    var poll = 30
    /// config.update, checked (nil = none or not usable)
    var update: UpdateInfo?
    /// the version config.update named, even if the rest was odd (to compare with what the poll says)
    var updateVersion: String?
    /// config.coffee if it is a buymeacoffee.com link, else the fixed one
    var coffee: URL = CoffeeLink.fallback
    /// config.act.apps: the programs the Spark may start on this Mac (set in the panel per device)
    var actApps: [ActApp] = []
    /// config.act.wait: hold GET /api/desk/wait so a wish of the Spark arrives at once (Rechner fernsteuern)
    var actWait = false
    /// config.wake.word
    var wakeWord = "Hey Spark"
    /// Version 4: config.meeting, config.home
    var v4 = V4Config()
    /// config.face: the face the admin picked in the panel (kept for the next start)
    var face = FaceKind.saved
    /// Antworten vorlesen of the profile (panel: Gespräch einstellen): off = Frag Spark never reads answers aloud
    var aloud = true
    /// config.office.web: Word, Excel and Outlook can be set up (the panel knows its https address)
    var officeWeb = false
    /// config.auslassen: sub folders of the watched folder the Spark never reads (Ich → Dokumente → Ausgelassene Ordner)
    var leftOut = LeftOut()

    init() {}

    init(_ d: [String: Any]) {
        rev = (d["rev"] as? NSNumber)?.intValue ?? 0
        profile = Self.plain(d["profile"] as? String ?? "", max: 80)
        let p = d["parts"] as? [String: Any] ?? [:]
        let a = d["allowed"] as? [String: Any] ?? [:]
        for name in Self.partNames {
            parts[name] = (p[name] as? Bool) ?? false
            allowed[name] = (a[name] as? Bool) ?? false
        }
        if let w = d["write"] as? [String: Any] {
            if let s = w["art"] as? String, !s.isEmpty { writeArt = s }
            if let s = w["sprache"] as? String, !s.isEmpty { writeSprache = s }
            if let s = w["wunsch"] as? String { writeWunsch = String(s.prefix(300)) }
            if let l = w["arts"] as? [String], !l.isEmpty { writeArts = l }
            if let b = w["preview"] as? Bool { preview = b }
        }
        if let s = (d["dictate"] as? [String: Any])?["sprache"] as? String,
           ["auto", "de", "en", "fr", "es", "it", "nl"].contains(s) {
            dictateSprache = s
        }
        autostart = d["autostart"] as? Bool
        let artList = (d["arts"] as? [[String: Any]] ?? []).compactMap { x -> ArtInfo? in
            guard let id = x["id"] as? String, let de = x["de"] as? String else { return nil }
            return ArtInfo(id: id, de: Self.plain(de, max: 40), changes: (x["changes"] as? Bool) ?? true)
        }
        if !artList.isEmpty { arts = artList }
        let langList = (d["langs"] as? [[String: Any]] ?? []).compactMap { x -> LangInfo? in
            guard let id = x["id"] as? String, let de = x["de"] as? String else { return nil }
            return LangInfo(id: id, de: Self.plain(de, max: 40))
        }
        if !langList.isEmpty { langs = langList }
        poll = min(max((d["poll"] as? NSNumber)?.intValue ?? 30, 10), 600)
        update = UpdateInfo(json: d["update"])
        updateVersion = (d["update"] as? [String: Any])?["version"] as? String
        coffee = CoffeeLink.accept(d["coffee"])
        actApps = ActApp.list((d["act"] as? [String: Any])?["apps"])
        actWait = (d["act"] as? [String: Any])?["wait"] as? Bool ?? false
        wakeWord = WakeWord.parse(d["wake"])
        v4 = V4Config(d)
        face = FaceKind(d["face"])
        aloud = d["aloud"] as? Bool ?? true
        officeWeb = (d["office"] as? [String: Any])?["web"] as? Bool ?? false
        leftOut = LeftOut(d["auslassen"])
        FaceKind.saved = face
    }

    /// the arts this device offers, in the Spark's order
    var offeredArts: [ArtInfo] {
        let list = arts.filter { writeArts.contains($0.id) }
        return list.isEmpty ? Array(arts.prefix(1)) : list
    }

    static func plain(_ s: String, max: Int) -> String {
        let one = s.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        return String(one.prefix(max))
    }
}

enum Reach {
    case unknown, ok, offline, notaus
}

/// The program's state: pairing, the Spark's config, the poll, the hotkeys, the menu-bar icon.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()

    @Published private(set) var base: String?
    @Published private(set) var config: DeskConfig?
    @Published private(set) var reach: Reach = .unknown
    @Published private(set) var reachText = ""
    @Published private(set) var hotkeys: [HotAction: Hotkey] = HotkeyStore.load()
    @Published private(set) var hotkeyProblem = ""
    @Published private(set) var autostartProblem = ""

    private(set) var client: SparkClient?
    private var loop: Task<Void, Never>?
    private var lastNote: Int?

    var paired: Bool { client != nil }

    /// "1.0.342", or "Entwicklungsversion"
    var version: String {
        Updater.currentVersion ?? "Entwicklungsversion"
    }

    /// this Mac's name as sent when pairing (asked once: Host can be slow)
    private(set) lazy var deviceName: String = SparkAddress.deviceName(Host.current().localizedName)

    /// the coffee link (from the Spark when it sent a valid one)
    var coffee: URL { config?.coffee ?? CoffeeLink.fallback }

    /// version and arch on every config and poll call
    private var versionQuery: String {
        "version=\(Updater.versionParam)&arch=mac"
    }

    static func offHint(_ name: String) -> String {
        "\(name) ist aus. Im Panel unter Ich → Begleiter einschalten."
    }

    func part(_ p: String) -> Bool { config?.parts[p] == true }

    func allowedPart(_ p: String) -> Bool { config?.allowed[p] == true }

    func hotkeyLabel(_ a: HotAction) -> String { hotkeys[a]?.label ?? "" }

    // ------------------------------------------------------------------ start, pairing

    func start() {
        HotkeyCenter.shared.install()
        HotkeyCenter.shared.onPress = { [weak self] a in self?.hotkey(a) }
        Notifier.setup()
        Updater.cleanOnStart()
        if let saved = Keychain.load(), let base = try? SparkAddress.checkBase(saved.base) {
            connect(base: base, key: saved.key)
        } else {
            Windows.showPairing()
        }
    }

    func connect(base: String, key: String) {
        loop?.cancel()
        client?.close()
        client = SparkClient(base: base, key: key)
        self.base = base
        config = nil
        lastNote = nil
        Updater.shared.reset()
        reach = .unknown
        reachText = "Verbinde …"
        applyHotkeys()
        applyParts()
        loop = Task { [weak self] in await self?.run() }
    }

    /// "Entkoppeln": the key goes from the keychain; the device stays in the panel until removed there.
    func unpair() {
        loop?.cancel()
        loop = nil
        client?.close()
        client = nil
        Keychain.delete()
        Updater.shared.reset()
        base = nil
        config = nil
        reach = .unknown
        reachText = ""
        applyHotkeys()
        applyParts()
    }

    /// 401: the Spark no longer knows the key.
    private func forgetDevice() {
        unpair()
        Windows.showPairing(message: SparkProblem.unknownDevice.message)
    }

    /// `hash` only fixed from the code, e.g. "#melden" (Probleme melden opens its window)
    func openPanel(_ hash: String = "") {
        guard let base, let url = URL(string: base + "/" + hash) else { return }
        NSWorkspace.shared.open(url)
    }

    // ------------------------------------------------------------------ poll

    private func run() async {
        while !Task.isCancelled {
            let wait = await cycle()
            if Task.isCancelled { return }
            try? await Task.sleep(nanoseconds: UInt64(wait) * 1_000_000_000)
        }
    }

    /// One poll (and the config when it is missing or its rev changed); the seconds until the next one.
    private func cycle() async -> Int {
        guard let client else { return 30 }
        do {
            if config == nil {
                try await loadConfig(client)
            }
            let mic = MicSwitch.shared.closed ? "closed" : "open"   // only this state, never sound
            // Meldung ans genutzte Gerät: seconds since the last input at this Mac (only the number, never what)
            let idle = Int(min(CGEventSource.secondsSinceLastEventType(.combinedSessionState,
                                                                          eventType: CGEventType(rawValue: ~0)!), 7 * 86400))
            let d = try await client.get("api/desk/poll?after=\(lastNote ?? 0)&mic=\(mic)&idle=\(idle)&\(versionQuery)")
            guard client === self.client else { return 1 }
            let pollUpdate = d["update"] as? String          // null or "1.0.350"
            if let rev = (d["rev"] as? NSNumber)?.intValue, rev != config?.rev {
                try await loadConfig(client)
            } else if pollUpdate != config?.updateVersion {
                try await loadConfig(client)
            }
            takePoll(d)
            return config?.poll ?? 30
        } catch is CancellationError {
            return 1
        } catch {
            guard client === self.client else { return 1 }
            absorb(error)
            if let p = error as? SparkProblem, case .notaus = p { return 60 }   // slower while a Notaus holds
            return config?.poll ?? 30
        }
    }

    private func loadConfig(_ client: SparkClient) async throws {
        let d = try await client.get("api/desk/config?\(versionQuery)")
        guard client === self.client else { return }
        let c = DeskConfig(d)
        config = c
        Updater.shared.take(c.update)
        applyHotkeys()
        applyParts()
        if let want = c.autostart { applyAutostart(want) }
        if ["notes", "actions", "folder", "inbox", "agenda", "daily", "post"].contains(where: { c.parts[$0] == true }) {
            Notifier.ask()
        }
        if reach == .unknown || reach == .offline {
            reach = .ok
            reachText = ""
        }
    }

    func refreshConfig() async {
        guard let client else { return }
        do {
            try await loadConfig(client)
        } catch {
            absorb(error)
        }
    }

    private func takePoll(_ d: [String: Any]) {
        if part("act") {
            ActCenter.shared.take(ActAsk.list(d["asks"]))
        }
        if part("inbox") {
            InboxCenter.shared.take(InboxItem.list(d["inbox"]))
        }
        if part("quiet") {
            Quiet.shared.pollTick()
        }
        let level = ((d["notaus"] as? [String: Any])?["level"] as? NSNumber)?.intValue ?? 0
        if level > 0 {
            reach = .notaus
            reachText = "Notaus Stufe \(level) ist an."
        } else if let su = d["spark_update"] as? [String: Any] {
            // the Spark's own update (like the panel and the iPhone): "Spark-Update läuft: 40 % · step"
            let pct = min(max((su["pct"] as? NSNumber)?.intValue ?? 0, 0), 100)
            let step = String(String((su["step"] as? String ?? "").unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }).prefix(40))
            reach = .ok
            reachText = "Spark-Update läuft: \(pct) %" + (step.isEmpty ? "" : " · \(step)")
        } else {
            reach = .ok
            reachText = ""
        }
        let last = (d["last"] as? NSNumber)?.intValue ?? 0
        guard let prev = lastNote else {
            // the first poll: notes from before the program started are not shown
            lastNote = last
            return
        }
        if part("notes") {
            let notes = (d["notes"] as? [[String: Any]] ?? []).compactMap {
                x -> (n: Int, title: String, body: String, tag: String, actions: [String], weg: String?)? in
                guard let n = (x["n"] as? NSNumber)?.intValue, n > prev else { return nil }
                // the way "Panel öffnen" goes (E-Mail → Für dich): only a way as Wege finds one in a text
                let weg = Wege.find(x["weg"] as? String ?? "")?.way
                let tag = x["tag"] as? String ?? ""
                // an important new mail (part post) has its own buttons: Antwort entwerfen, Gelesen, Ansehen
                let acts = tag == NoteActions.mailTag ? NoteActions.parseMail(x["actions"]) : NoteActions.parse(x["actions"])
                return (n, x["title"] as? String ?? "", x["body"] as? String ?? "", tag, acts, weg)
            }
            if notes.contains(where: { $0.tag == NoteActions.mailTag }) {
                Task { await PostCenter.shared.refresh() }   // the numbers under "Post" at once
            }
            for note in notes.sorted(by: { $0.n < $1.n }).suffix(5) {
                var buttons = part("actions") ? note.actions.filter { $0 != "draft" || part("ask") } : []
                if part("agenda") && !buttons.contains("fdremind") && note.tag != NoteActions.mailTag { buttons.append("remind") }
                Notifier.show(title: note.title, body: note.body, tag: note.tag, id: "note-\(note.n)",
                              note: note.n, actions: buttons, weg: note.weg)
            }
        }
        // last smaller than before: the Spark started anew
        lastNote = last
    }

    /// Applies what an error means for the program (contract, "Errors") and gives the text to show.
    @discardableResult
    func absorb(_ error: Error) -> String {
        guard let p = error as? SparkProblem else {
            return "Unerwarteter Fehler."
        }
        switch p {
        case .unknownDevice:
            forgetDevice()
        case .off:
            Task { await self.refreshConfig() }
        case .busy, .failed, .conflict:
            break
        case .notaus(let m):
            reach = .notaus
            reachText = m
        case .offline(let m):
            if reach != .notaus || config == nil {
                // while the Spark's update ran, this is the restart that belongs to it
                let restart = reach == .ok && reachText.hasPrefix("Spark-Update läuft")
                reach = .offline
                reachText = restart ? "Spark startet für das Update neu …" : m
            }
        }
        return p.message
    }

    // ------------------------------------------------------------------ autostart (from the panel)

    private func applyAutostart(_ want: Bool) {
        let s = SMAppService.mainApp
        do {
            if want && (s.status == .notRegistered || s.status == .notFound) {
                try s.register()
            } else if !want && (s.status == .enabled || s.status == .requiresApproval) {
                try s.unregister()
            }
            autostartProblem = s.status == .requiresApproval
                ? "Autostart wartet auf Freigabe: Systemeinstellungen → Allgemein → Anmeldeobjekte." : ""
        } catch {
            autostartProblem = "Autostart ließ sich nicht einrichten (Programm in den Ordner „Programme“ legen)."
        }
    }

    var autostartOn: Bool { SMAppService.mainApp.status == .enabled }

    // ------------------------------------------------------------------ hotkeys

    /// Registers the hotkeys of the parts that are on; the others have none.
    func applyHotkeys() {
        let hc = HotkeyCenter.shared
        hc.unregisterAll()
        var taken: [String] = []
        if paired {
            for a in HotAction.allCases where part(a.part) {
                if let hk = hotkeys[a], !hc.register(a, hk) {
                    taken.append("\(hk.label) (\(a.title))")
                }
            }
        }
        hotkeyProblem = taken.isEmpty ? ""
            : "Schon von macOS oder einem anderen Programm belegt: " + taken.joined(separator: ", ")
    }

    /// A new combination from the settings window; an error text or nil.
    func setHotkey(_ a: HotAction, _ hk: Hotkey) -> String? {
        if let other = HotAction.allCases.first(where: { $0 != a && hotkeys[$0]?.same(as: hk) == true }) {
            return "\(hk.label) ist schon für „\(other.title)“ vergeben."
        }
        hotkeys[a] = hk
        HotkeyStore.save(hk, for: a)
        applyHotkeys()
        return nil
    }

    private func hotkey(_ a: HotAction) {
        switch a {
        case .write:
            Task { await startWrite(fromMenu: false) }
        case .ask:
            openAsk()
        case .screen:
            ScreenAsk.start()
        case .mail:
            MailDraft.start(front: frontApp())
        case .speak:
            Speaker.shared.toggle()
        case .meeting:
            Meeting.shared.toggle()
        case .capture:
            CaptureController.open(fromHotkey: true)
        case .dictate:
            if NSApp.isActive, let key = NSApp.keyWindow, key === Windows.shared.window("ask") {
                Dictation.shared.toggle(.ask)
            } else {
                Dictation.shared.toggle(.cursor(frontApp()))
            }
        }
    }

    func frontApp() -> NSRunningApplication? {
        let f = NSWorkspace.shared.frontmostApplication
        return f == NSRunningApplication.current ? nil : f
    }

    // ------------------------------------------------------------------ parts

    /// Schreibhilfe: from the hotkey the marked text is copied (with Accessibility); from the menu the window
    /// opens empty and the result goes to the clipboard.
    func startWrite(fromMenu: Bool) async {
        guard paired else {
            Windows.showPairing()
            return
        }
        guard part("write") else {
            HUD.show(Self.offHint("Die Schreibhilfe"))
            return
        }
        let target = fromMenu ? nil : frontApp()
        let category = fromMenu ? nil : appCategory(target)
        var text = ""
        if !fromMenu {
            if Access.trusted {
                text = await Clip.copySelection() ?? ""
            } else {
                Access.askOnce()
            }
        }
        let cfg = config ?? DeskConfig()
        let core = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !fromMenu && Access.trusted && !cfg.preview && !core.isEmpty, let client {
            await writeDirect(text, cfg: cfg, client: client, target: target, category: category)
            return
        }
        WriteController.open(text: text, target: fromMenu ? .menu : .hotkey(target), config: cfg, app: category)
    }

    /// Without preview (set in the panel): improve and paste right away.
    private func writeDirect(_ text: String, cfg: DeskConfig, client: SparkClient, target: NSRunningApplication?,
                             category: String?) async {
        let parts = WriteController.split(text)
        guard parts.core.count <= SparkClient.writeMax else {
            HUD.show("Der Text ist zu lang (höchstens \(SparkClient.writeMax) Zeichen).")
            return
        }
        HUD.show("Spark arbeitet …", symbol: "hourglass", seconds: 200)
        do {
            let art = cfg.writeArt
            let r = try await client.improve(text: parts.core, art: art,
                                             sprache: art == "uebersetzen" ? cfg.writeSprache : nil, wunsch: cfg.writeWunsch,
                                             app: category)
            HUD.hide()
            let out = parts.lead + r.text.trimmingCharacters(in: .whitespacesAndNewlines) + parts.trail
            if await Clip.paste(out, into: target) {
                HUD.show(WriteController.changesText(r), symbol: "checkmark.circle")
            } else {
                HUD.show("Text ist in der Zwischenablage (⌘V fügt ihn ein).", symbol: "doc.on.clipboard")
            }
        } catch is CancellationError {
            HUD.hide()
        } catch {
            HUD.show(absorb(error), symbol: "exclamationmark.triangle")
        }
    }

    /// Part "context": the category of the app that was in front when the hotkey came (nil when the part is off).
    /// Only the category ("mail", "browser", …) leaves the Mac, never a name or a title.
    func appCategory(_ app: NSRunningApplication?) -> String? {
        guard part("context"), let app else { return nil }
        return AppCategory.of(bundleID: app.bundleIdentifier)
    }

    /// Starts or stops what runs on its own (folder, wake word) and the notification buttons, after the config.
    func applyParts() {
        let on = paired && config != nil
        FolderWatch.shared.apply(on: on && part("folder"))
        Wake.shared.apply(on: on && part("wake"))
        if !(on && part("act")) { ActCenter.shared.clear() }
        InstalledApps.shared.apply(on: on && part("act"))
        ActWait.shared.apply(on: on && (part("act") || part("view")))
        ViewCenter.shared.apply(on: on && part("view"))
        if !(on && part("inbox")) { InboxCenter.shared.clear() }
        Speaker.shared.apply(on: on && part("speak"))
        AgendaCenter.shared.apply(on: on && part("agenda"))
        PostCenter.shared.apply(on: on && part("post"))
        ListsCenter.shared.apply(on: on && part("lists"))
        Quiet.shared.apply(on: on && part("quiet"))
        Meeting.shared.apply(on: on && part("meeting"))
        HomeCenter.shared.apply(on: on && part("home"), configured: config?.v4.homeButtons ?? [])
        Daily.shared.apply(on: on && part("daily"))
        OfficeSetup.apply(on: on && part("office"))
        Notifier.registerCategories()
    }

    func openAsk() {
        guard paired else {
            Windows.showPairing()
            return
        }
        guard part("ask") else {
            HUD.show(Self.offHint("Frag Spark"))
            return
        }
        AskController.open()
    }

    /// The field "Frag Spark …" in the tray panel: open Frag Spark and ask the typed question right away (empty = only open).
    func askFromPanel(_ question: String) {
        openAsk()
        guard paired, part("ask"), !question.isEmpty else { return }
        let c = AskController.shared
        c.input = question
        c.send()
    }

    /// The microphone in that field: open Frag Spark and listen there at once (only with part "dictate", mic open).
    func askByVoice() {
        openAsk()
        guard paired, part("ask"), part("dictate"), !MicSwitch.shared.closed, !Dictation.shared.recording else { return }
        Dictation.shared.toggle(.ask)
    }

    func confirmNotaus() {
        guard part("notaus"), let client else { return }
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.alertStyle = .critical
        a.messageText = "Mein Notaus auslösen?"
        a.informativeText = """
            Der Spark hält dann für dein Profil alles an, was er für dich tut. Auch dieser Begleiter bekommt \
            keine Antworten mehr.

            Aufheben geht nur im Panel im Browser, mit deiner PIN.
            """
        let go = a.addButton(withTitle: "Notaus auslösen")
        go.hasDestructiveAction = true
        a.addButton(withTitle: "Abbrechen")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        ViewCenter.shared.stop(tell: false)   // a running screen session ends at once, also without the Spark
        Task {
            do {
                _ = try await client.postJSON("api/desk/notaus", [:], timeout: 30)
                reach = .notaus
                reachText = "Mein Notaus ist an."
                let done = NSAlert()
                done.messageText = "Mein Notaus ist an."
                done.informativeText = "Aufheben geht nur im Panel im Browser, mit deiner PIN."
                done.addButton(withTitle: "Panel öffnen")
                done.addButton(withTitle: "OK")
                NSApp.activate(ignoringOtherApps: true)
                if done.runModal() == .alertFirstButtonReturn { openPanel() }
            } catch {
                HUD.show(absorb(error), symbol: "exclamationmark.triangle")
            }
        }
    }

    // ------------------------------------------------------------------ menu bar

    var statusLine: String {
        guard paired else { return "Nicht gekoppelt" }
        switch reach {
        case .unknown: return "Verbinde mit dem Spark …"
        case .ok:
            if !reachText.isEmpty { return reachText }
            let p = config?.profile ?? ""
            return p.isEmpty ? "Spark erreichbar" : "Spark erreichbar · \(p)"
        case .offline: return reachText.isEmpty ? "Spark nicht erreichbar" : reachText
        case .notaus: return reachText.isEmpty ? "Notaus ist an" : reachText
        }
    }

    /// The face in the menu bar: a template silhouette when all is well, with a coloured dot otherwise
    /// (grey not reachable, red Notaus, accent when an update is there).
    var menuIcon: NSImage {
        MenuIcon.image(dot: menuDot, moon: paired && part("quiet") && Quiet.shared.busy, face: face,
                       micClosed: paired && usesMic && MicSwitch.shared.closed)
    }

    /// parts that can open the microphone (the mic buttons in the windows belong to "dictate")
    var usesMic: Bool {
        part("dictate") || part("ask") || part("wake") || part("meeting")
    }

    /// the face for every window and the menu bar: the Spark's choice, before the first config the last one
    var face: FaceKind { config?.face ?? FaceKind.saved }

    var menuDot: MenuIcon.Dot {
        if !paired { return .grey }
        if reach == .notaus { return .red }                      // always, whether "status" is on or not
        if part("status") && reach == .offline { return .grey }
        if Wake.shared.listening { return .listening }
        if Updater.shared.dot { return .accent }
        return .plain
    }

    /// the pill in the panel's header
    var reachPill: (text: String, color: Color) {
        guard paired else { return ("nicht gekoppelt", Theme.muted) }
        switch reach {
        case .unknown: return ("verbinde …", Theme.muted)
        case .ok: return ("verbunden", Theme.ok)
        case .offline: return ("nicht erreichbar", Theme.muted)
        case .notaus: return ("Notaus", Theme.bad)
        }
    }
}

// ------------------------------------------------------------------ notifications ("Meldungen")

final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    /// The buttons of a note (part "actions"): Antworten (with text), Später, Panel öffnen.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let action = response.actionIdentifier
        let typed = (response as? UNTextInputNotificationResponse)?.userText ?? ""
        let req = response.notification.request
        let note = (req.content.userInfo["note"] as? NSNumber)?.intValue
        let weg = req.content.userInfo["weg"] as? String
        let title = req.content.title
        let body = req.content.body
        let thread = req.content.threadIdentifier
        let category = req.content.categoryIdentifier
        Task { @MainActor in
            Notifier.handle(action: action, typed: typed, note: note, title: title, body: body, thread: thread,
                            category: category, weg: weg)
        }
        completionHandler()
    }
}

@MainActor
enum Notifier {
    private static let delegate = NotificationDelegate()
    private static var asked = false
    static let laterSeconds: TimeInterval = 3600

    static func setup() {
        UNUserNotificationCenter.current().delegate = delegate
        registerCategories()
    }

    static func ask() {
        guard !asked else { return }
        asked = true
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// One category per combination of buttons, so each note shows exactly the buttons the Spark gave it.
    static func registerCategories() {
        var set = Set<UNNotificationCategory>()
        for combo in NoteActions.allCombinations4 {
            guard let id = NoteActions.category4(combo) else { continue }
            let actions: [UNNotificationAction] = combo.map { a in
                switch a {
                case "reply":
                    return UNTextInputNotificationAction(identifier: "reply", title: "Antworten", options: [],
                                                         textInputButtonTitle: "Senden",
                                                         textInputPlaceholder: "Antwort an den Spark …")
                case "later":
                    return UNNotificationAction(identifier: "later", title: "Später", options: [])
                case "remind":
                    return UNNotificationAction(identifier: "remind", title: "In 20 Min erinnern", options: [])
                case "done", "fdremind":
                    return UNNotificationAction(identifier: a, title: NoteActions.panelLabel(a) ?? a, options: [])
                default:
                    return UNNotificationAction(identifier: "open", title: "Panel öffnen", options: [.foreground])
                }
            }
            set.insert(UNNotificationCategory(identifier: id, actions: actions, intentIdentifiers: [], options: []))
        }
        // a new mail: sender and subject only after unlocking when previews are hidden (hiddenPreviewsBodyPlaceholder)
        for combo in NoteActions.mailCombinations {
            guard let id = NoteActions.mailCategory(combo) else { continue }
            let actions: [UNNotificationAction] = combo.map { a in
                switch a {
                case "draft": return UNNotificationAction(identifier: "draft", title: "Antwort entwerfen", options: [.foreground])
                case "read": return UNNotificationAction(identifier: "read", title: NoteActions.panelLabel(a) ?? a, options: [])
                default: return UNNotificationAction(identifier: "open", title: "Ansehen", options: [.foreground])
                }
            }
            set.insert(UNNotificationCategory(identifier: id, actions: actions, intentIdentifiers: [],
                                              hiddenPreviewsBodyPlaceholder: "Neue Mail", options: []))
        }
        set.insert(UNNotificationCategory(identifier: inboxFileCategory,
                                          actions: [UNNotificationAction(identifier: "openFolder", title: "Ordner öffnen",
                                                                         options: [.foreground])],
                                          intentIdentifiers: [], options: []))
        UNUserNotificationCenter.current().setNotificationCategories(set)
    }

    /// The Spark's note as plain text; with buttons when the part "actions" is on and the note has some.
    static func show(title: String, body: String, tag: String, id: String, note: Int? = nil, actions: [String] = [],
                     weg: String? = nil) {
        let c = UNMutableNotificationContent()
        c.title = DeskConfig.plain(title, max: 200).isEmpty ? "Spark" : DeskConfig.plain(title, max: 200)
        c.body = String(body.prefix(1500))
        c.sound = .default
        if !tag.isEmpty { c.threadIdentifier = String(tag.prefix(20)) }
        var info: [String: Any] = [:]
        if let note { info["note"] = note }
        if let weg { info["weg"] = weg }
        if !info.isEmpty { c.userInfo = info }
        if let cat = tag == NoteActions.mailTag ? NoteActions.mailCategory(actions) : NoteActions.category4(actions) {
            c.categoryIdentifier = cat
        }
        let r = UNNotificationRequest(identifier: id, content: c, trigger: nil)
        UNUserNotificationCenter.current().add(r) { _ in }
    }

    static func handle(action: String, typed: String, note: Int?, title: String, body: String, thread: String,
                       category: String, weg: String? = nil) {
        let model = AppModel.shared
        switch action {
        case "reply":
            guard model.part("actions") else { return HUD.show(AppModel.offHint("Knöpfe in Meldungen")) }
            let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty {
                AskController.openForNote(note, title: title, body: body)
            } else {
                AskController.shared.run(question: "Antwort auf „\(DeskConfig.plain(title, max: 80))“: \(text)",
                                         notify: true) { client in
                    try await client.ask(text, note: note)
                }
            }
        case "later":
            let c = UNMutableNotificationContent()
            c.title = title
            c.body = body
            c.sound = .default
            if !thread.isEmpty { c.threadIdentifier = thread }
            var info: [String: Any] = [:]
            if let note { info["note"] = note }
            if let weg { info["weg"] = weg }
            if !info.isEmpty { c.userInfo = info }
            if !category.isEmpty { c.categoryIdentifier = category }
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: laterSeconds, repeats: false)
            let r = UNNotificationRequest(identifier: "later-\(note ?? 0)-\(UUID().uuidString)", content: c, trigger: trigger)
            UNUserNotificationCenter.current().add(r) { _ in }
        case "open":
            // the note's way (E-Mail → Für dich), else the start page
            if let weg, let url = Wege.link(weg, base: model.base) {
                NSWorkspace.shared.open(url)
            } else {
                model.openPanel()
            }
        case "draft":
            // Antwort entwerfen to a new mail: Frag Spark with the note in front and the request in the field, not sent
            guard model.part("actions"), model.part("ask") else { return HUD.show(AppModel.offHint("Frag Spark")) }
            AskController.openForNote(note, title: title, body: body)
            AskController.shared.input = NoteActions.draftQuestion
        case "done", "fdremind", "read":
            // a button of a note about a Für-dich card or a new mail: the Spark checks the note and what is behind it
            guard model.part("actions") else { return HUD.show(AppModel.offHint("Knöpfe in Meldungen")) }
            guard let note, let client = model.client else { return }
            Task { @MainActor in
                do {
                    let text = try await client.noteAct(note: note, act: action)
                    Notifier.plain(title: "Spark", body: text)
                } catch {
                    Notifier.plain(title: "Spark", body: model.absorb(error))
                }
            }
        case "remind":
            AgendaCenter.shared.remind(note: note, text: note == nil ? DeskConfig.plain(title, max: 300) : nil)
        case "openFolder":
            InboxCenter.revealFolder()
        default:
            if category == inboxFileCategory && action == UNNotificationDefaultActionIdentifier {
                InboxCenter.revealFolder()
            }
        }
    }

    static let inboxFileCategory = "inbox.file"

    /// "Vom Spark: <name>" with the button "Ordner öffnen"
    static func inboxFile(name: String) {
        let c = UNMutableNotificationContent()
        c.title = "Vom Spark"
        c.body = "Datei gespeichert: Downloads/\(InboxCenter.folderName)/\(name)"
        c.sound = .default
        c.categoryIdentifier = inboxFileCategory
        let r = UNNotificationRequest(identifier: "inbox-\(UUID().uuidString)", content: c, trigger: nil)
        UNUserNotificationCenter.current().add(r) { _ in }
    }

    /// A short message of the program itself ("3 Dateien ins Wissen übernommen", the Spark's answer).
    static func plain(title: String, body: String) {
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = String(body.prefix(1500))
        c.sound = .default
        let r = UNNotificationRequest(identifier: "begleiter-\(UUID().uuidString)", content: c, trigger: nil)
        UNUserNotificationCenter.current().add(r) { _ in }
    }
}
