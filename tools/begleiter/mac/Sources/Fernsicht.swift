import AppKit
import Carbon
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Rechner fernsteuern (Dominik 2026-10-17), Stufe 2: Bildschirm zeigen und bedienen (fernsicht.py in the panel).
// The request comes with the wait of Stufe 1 (part "view"). This Mac asks first (Ablehnen / Nur ansehen /
// Erlauben); while it runs it shows a red frame and a bar with „Beenden“, sends at most four pictures a second of
// the main display (JPEG, only in memory; screencapture's file lives in a private folder and is deleted at once)
// and, only after „Erlauben“, carries out clicks, moves, scrolling, keys from a fixed list and typed text.
// No ⌘-Tab, no ⌘-Space, no free key combination.
// Stufe 3 (bedienen.py, "operate"): nobody watches; the Spark hands one step at a time ("step"), each shown here
// with its target marked and done only after „Erlauben“. Our own windows are left out of the pictures.
// Picture, keys, inputs, frame, bar and question come from the core Sicht.swift (shared with SparkHilfe).
// „Bildschirm beschreiben“ ("look"): asked like the rest; the panel takes one picture and ends the session.

struct ViewAsk: Equatable {
    let id: String
    let control: Bool
    var operate = false
    var task = ""
    /// „Bildschirm beschreiben“: the Spark looks once (task holds the person's question)
    var look = false

    /// the "views" of GET /api/desk/wait, every value checked
    static func list(_ raw: Any?) -> [ViewAsk] {
        guard let arr = raw as? [[String: Any]] else { return [] }
        return arr.prefix(4).compactMap { d in
            guard let id = d["id"] as? String, (1...64).contains(id.count),
                  id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }) else { return nil }
            let want = d["want"] as? String ?? "view"
            let task = DeskConfig.plain(d["task"] as? String ?? "", max: 300)
            if (want == "operate" || want == "look") && task.isEmpty { return nil }   // no task, no operating or looking
            return ViewAsk(id: id, control: want == "control" || want == "operate", operate: want == "operate", task: task,
                           look: want == "look")
        }
    }
}

/// Asks at this Mac and keeps the one running session.
@MainActor
final class ViewCenter {
    static let shared = ViewCenter()
    private var asking = false
    private var session: ViewSession?

    var running: Bool { session != nil }

    /// part off or Begleiter unpaired: what runs ends
    func apply(on: Bool) {
        if !on { stop(tell: true) }
    }

    func take(_ asks: [ViewAsk]) {
        guard let ask = asks.first, !asking, AppModel.shared.part("view") else { return }
        asking = true
        stop(tell: true)                      // a new request ends the old session
        let mode = consent(ask)
        Task { @MainActor in
            defer { self.asking = false }
            guard let client = AppModel.shared.client else { return }
            do {
                let d = try await client.postJSON("api/desk/view/answer", ["id": ask.id, "mode": mode], timeout: 20)
                let state = d["state"] as? String ?? "ended"
                guard state == "view" || state == "control" else { return }
                let s = ViewSession(id: ask.id, control: state == "control", client: client, task: ask.operate ? ask.task : nil)
                self.session = s
                s.start()
            } catch {
                _ = AppModel.shared.absorb(error)
            }
        }
    }

    func stop(tell: Bool) {
        let s = session
        session = nil
        s?.stop(tell: tell)
    }

    fileprivate func ended(_ s: ViewSession) {
        if session === s { session = nil }
    }

    /// "no", "view" or "control"; "Ablehnen" is the first button, so Return alone shows nothing
    private func consent(_ ask: ViewAsk) -> String {
        let message: String, info: String
        if ask.operate {
            message = "Spark möchte an diesem Mac deinen Auftrag Schritt für Schritt erledigen: „\(ask.task)“"
            info = """
                Nur, wenn du das gerade selbst gesagt hast. Jeden Schritt zeigt der Begleiter mit markiertem Ziel und \
                fragt; „Stopp“ beendet es sofort. Der Spark sieht dafür den Bildschirm, gespeichert wird nichts.

                Ohne Antwort gilt nach 60 Sekunden „Ablehnen“.
                """
        } else if ask.look {
            message = "Spark möchte einmal auf diesen Bildschirm sehen, um deine Frage zu beantworten: „\(ask.task)“"
            info = """
                Nur, wenn du das gerade selbst gefragt hast. Der Spark nimmt ein einziges Bild auf und beschreibt es dir; \
                gespeichert wird nichts, auch nicht im Verlauf.

                Ohne Antwort gilt nach 60 Sekunden „Ablehnen“.
                """
        } else {
            message = ask.control
                ? "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen und bedienen."
                : "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen."
            info = """
                Nur, wenn du das gerade selbst angestoßen hast. Solange es läuft, siehst du einen roten Rahmen und oben \
                „Beenden“. Es wird nichts aufgezeichnet.

                Ohne Antwort gilt nach 60 Sekunden „Ablehnen“.
                """
        }
        let buttons = ask.operate || ask.look ? ["Ablehnen", "Erlauben"]
            : ask.control ? ["Ablehnen", "Nur ansehen", "Erlauben"] : ["Ablehnen", "Nur ansehen"]
        let r = ViewAlert.ask(message: message, info: info, buttons: buttons, timeout: ActCenter.timeout)
        var mode = ask.look ? (r == 1 ? "view" : "no")
            : ask.operate ? (r == 1 ? "control" : "no")
            : r == 1 ? "view" : (r == 2 && ask.control ? "control" : "no")
        if mode != "no" && !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
            HUD.show("Bildschirm zeigen braucht die Freigabe „Bildschirmaufnahme“; danach den Begleiter neu starten.",
                     symbol: "exclamationmark.triangle", seconds: 8)
            ScreenAsk.openSettings()
            return "no"
        }
        if mode == "control" && !Access.trusted {
            HUD.show("Bedienen braucht die Freigabe „Bedienungshilfen“" + (ask.operate ? "." : "; jetzt nur ansehen."),
                     symbol: "hand.raised", seconds: 6)
            mode = ask.operate ? "no" : "view"
        }
        return mode
    }
}

/// One running session: the red frame and the bar, the pictures out, the inputs in.
@MainActor
final class ViewSession: NSObject {
    let id: String
    let control: Bool
    /// Stufe 3: the task the Spark works on (only shown); nil for looking and operating from the panel
    let task: String?
    private let client: SparkClient
    private let display = CGMainDisplayID()
    private var tasks: [Task<Void, Never>] = []
    private var windows: [NSWindow] = []
    private var marks: ViewMarks?
    private var stopped = false

    init(id: String, control: Bool, client: SparkClient, task: String? = nil) {
        self.id = id
        self.control = control
        self.client = client
        self.task = task
    }

    func start() {
        marks = ViewMarks(display: display,
                          text: task.map { "Spark bedient deinen Mac: " + String($0.prefix(60)) }
                              ?? (control ? "Spark: dein Bildschirm wird gezeigt und bedient" : "Spark: dein Bildschirm wird gezeigt"),
                          end: "Beenden") { [weak self] in self?.stop(tell: true) }
        tasks.append(Task { @MainActor in await self.frames() })
        if control {
            tasks.append(Task { @MainActor in await self.inputs() })
        }
    }

    func stop(tell: Bool) {
        guard !stopped else { return }
        stopped = true
        tasks.forEach { $0.cancel() }
        tasks = []
        windows.forEach { $0.orderOut(nil) }
        windows = []
        marks?.close()
        marks = nil
        if tell {
            let client = client, id = id
            Task { @MainActor in _ = try? await client.postJSON("api/desk/view/end", ["id": id], timeout: 20) }
        }
        ViewCenter.shared.ended(self)
    }

    /// part off, key gone or a Notaus: stop at once instead of trying again
    private static func final(_ error: Error) -> Bool {
        guard let p = error as? SparkProblem else { return false }
        switch p {
        case .unknownDevice, .off, .notaus: return true
        default: return false
        }
    }

    private func frames() async {
        var last: Data?
        var sent = Date.distantPast
        var errors = 0
        while !Task.isCancelled && !stopped {
            let front = NSWorkspace.shared.frontmostApplication
            let app = Self.query(front?.localizedName ?? ""), exe = Self.query(front?.bundleURL?.path ?? "")
            let shot = await Task.detached(priority: .userInitiated) { ViewShot.take() }.value
            if let shot {
                if shot.data != last || Date().timeIntervalSince(sent) > 5 {
                    do {
                        let d = try await client.postData(
                            "api/desk/view/frame?id=\(id)&w=\(shot.width)&h=\(shot.height)&app=\(app)&exe=\(exe)",
                            shot.data, contentType: "image/jpeg", timeout: 20)
                        last = shot.data
                        sent = Date()
                        errors = 0
                        let st = d["state"] as? String ?? "ended"
                        if st != "view" && st != "control" {
                            stop(tell: false)
                            return
                        }
                    } catch {
                        errors += 1
                        if stopped { return }
                        if Self.final(error) || errors >= 3 {
                            stop(tell: false)
                            return
                        }
                    }
                }
            } else {
                errors += 1
                if errors >= 3 {
                    HUD.show("Der Bildschirm ließ sich nicht aufnehmen.", symbol: "exclamationmark.triangle")
                    stop(tell: true)
                    return
                }
            }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }
    }

    private func inputs() async {
        var errors = 0
        while !Task.isCancelled && !stopped {
            do {
                let d = try await client.get("api/desk/view/input?id=\(id)", timeout: 60)
                errors = 0
                let st = d["state"] as? String ?? "ended"
                guard st == "control" else {
                    if st != "view" { stop(tell: false) }
                    return
                }
                for e in (d["events"] as? [[String: Any]] ?? []).prefix(200) where !stopped {
                    if task != nil {
                        if e["t"] as? String == "step" { await step(e) }
                    } else {
                        apply(e)
                    }
                }
            } catch {
                errors += 1
                if stopped { return }
                if Self.final(error) || errors >= 3 {
                    stop(tell: false)
                    return
                }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    /// the front program's name or path for the picture's address (cut, percent-encoded)
    private static func query(_ s: String) -> String {
        String(DeskConfig.plain(s, max: 200)).addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }

    /// Stufe 3: show one step (target marked), ask, do it after „Erlauben“, tell the Spark
    private func step(_ e: [String: Any]) async {
        guard let n = (e["n"] as? NSNumber)?.intValue else { return }
        let kind = e["kind"] as? String ?? ""
        let before = NSWorkspace.shared.frontmostApplication
        let target = ["click", "double", "right"].contains(kind) ? point(e) : nil
        let marker = target.map { showMarker($0) }
        var answer = confirm(e, kind: kind, n: n)
        marker?.orderOut(nil)
        guard !stopped else { return }
        var error = ""
        if answer == "done" && kind != "ask" {
            if !Access.trusted {
                answer = "failed"
                error = "Die Freigabe Bedienungshilfen fehlt."
            } else {
                if let before, before.processIdentifier != ProcessInfo.processInfo.processIdentifier {
                    before.activate(options: [])
                    try? await Task.sleep(nanoseconds: 250_000_000)
                }
                if let mapped = Self.input(e, kind: kind) {
                    apply(mapped)
                } else {
                    answer = "failed"
                    error = "Diesen Schritt kennt der Begleiter nicht."
                }
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
        }
        var body: [String: Any] = ["id": id, "n": n, "answer": answer]
        if !error.isEmpty { body["error"] = error }
        do {
            _ = try await client.postJSON("api/desk/view/step", body, timeout: 20)
        } catch {
            stop(tell: true)
            return
        }
        if answer == "stop" { stop(tell: true) }
    }

    /// the step as one of the panel-style inputs apply() knows; nil for anything unknown
    private static func input(_ e: [String: Any], kind: String) -> [String: Any]? {
        switch kind {
        case "click", "double", "right":
            return ["t": "click", "x": e["x"] ?? -1, "y": e["y"] ?? -1, "b": kind == "click" ? "left" : kind]
        case "scroll": return ["t": "scroll", "dy": e["dy"] ?? 0]
        case "key": return ["t": "key", "k": e["k"] ?? ""]
        case "type": return ["t": "text", "s": e["s"] ?? ""]
        default: return nil
        }
    }

    /// "done", "skip" or "stop"; "Stopp" is the first button, so Return alone does nothing
    private func confirm(_ e: [String: Any], kind: String, n: Int) -> String {
        let why = DeskConfig.plain(e["why"] as? String ?? "", max: 160)
        let warn = DeskConfig.plain(e["warn"] as? String ?? "", max: 160)
        let of = max(n, (e["of"] as? NSNumber)?.intValue ?? n)
        let what: String
        switch kind {
        case "ask": what = why
        case "click": what = "Klick (rot markiert): " + why
        case "double": what = "Doppelklick (rot markiert): " + why
        case "right": what = "Rechtsklick (rot markiert): " + why
        case "scroll": what = (((e["dy"] as? NSNumber)?.intValue ?? 0) > 0 ? "Nach oben scrollen: " : "Nach unten scrollen: ") + why
        case "key": what = "Taste „\(DeskConfig.plain(e["k"] as? String ?? "", max: 20))“: " + why
        case "type": what = "Tippt: „\(DeskConfig.plain(e["s"] as? String ?? "", max: 200))“ – " + why
        default: what = why
        }
        let r = ViewAlert.ask(message: kind == "ask" ? "Spark fragt nach" : "Spark, Schritt \(n) von \(of)",
                              info: what + (warn.isEmpty ? "" : "\n\n⚠️ " + warn) + "\n\nOhne Antwort gilt nach 60 Sekunden „Stopp“.",
                              buttons: kind == "ask" ? ["Stopp", "Nein", "Weiter"] : ["Stopp", "Überspringen", "Erlauben"],
                              timeout: ActCenter.timeout, hidden: true, level: .screenSaver)
        return r == 2 ? "done" : r == 1 ? "skip" : "stop"
    }

    /// a red ring around the click's target (CG coordinates, top left), left out of the pictures
    private func showMarker(_ p: CGPoint) -> NSWindow {
        let size: CGFloat = 44
        let top = NSScreen.screens.first?.frame.maxY ?? CGDisplayBounds(display).height
        let w = NSWindow(contentRect: NSRect(x: p.x - size / 2, y: top - p.y - size / 2, width: size, height: size),
                         styleMask: .borderless, backing: .buffered, defer: false)
        w.isReleasedWhenClosed = false
        w.isOpaque = false
        w.backgroundColor = .clear
        w.ignoresMouseEvents = true
        w.level = .screenSaver
        w.sharingType = .none
        let v = NSView(frame: NSRect(x: 0, y: 0, width: size, height: size))
        v.wantsLayer = true
        v.layer?.cornerRadius = size / 2
        v.layer?.borderColor = Theme.nsBad.cgColor
        v.layer?.borderWidth = 5
        w.contentView = v
        w.orderFrontRegardless()
        windows.append(w)
        return w
    }

    private func point(_ e: [String: Any]) -> CGPoint? {
        ViewInput.point(e, display: display)
    }

    /// one input (the core checks and skips anything unknown)
    private func apply(_ e: [String: Any]) {
        ViewInput.apply(e, display: display)
    }
}
