import AppKit

/// Eine Hilfe über WSS (spontansteuern.py): erste Nachricht der Einmal-Schlüssel, dann erst den Namen des Helfers
/// zeigen und fragen (Ablehnen / Nur ansehen / Erlauben, 60 Sekunden ohne Antwort: Ablehnen); danach Bilder (JPEG,
/// höchstens `Ereignisse.maxFrame` Bytes, höchstens vier je Sekunde) hin und Eingaben zurück, nur aus den festen Listen
/// des Kerns, nur nach „Erlauben“ und nur solange der Helfer „Steuern“ gewählt hat. Kein Origin-Kopf, keine eigene
/// Zertifikatsprüfung, keine Weiterleitung, kein anderes Ziel, keine Cookies. Bild und Eingaben liegen nur im Speicher.
@MainActor
final class Sitzung {
    private static let wait: UInt64 = 20_000_000_000
    private static let keepAlive: TimeInterval = 5
    private static let helperMax = 60

    private let ziel: Ziel
    private let status: StatusFenster
    private let display = CGMainDisplayID()
    private let session: URLSession
    private var ws: URLSessionWebSocketTask?
    private var marks: ViewMarks?
    private var frames: Task<Void, Never>?
    private var helper = ""
    private var mode = ""
    private var steuern = false
    private var stopped = false
    private var greeted = false
    /// what the program says in the end instead of „beendet“ (the bar's „Beenden“: nothing, just close)
    private var quiet = false

    init(ziel: Ziel, status: StatusFenster) {
        self.ziel = ziel
        self.status = status
        session = Self.sitzung()
    }

    /// The connection's settings, the same for the program and its self-test (Pruefung/main.swift): no cookies, no
    /// cache, no stored credentials, normal TLS checks (no delegate), no Origin header of our own.
    nonisolated static func sitzung() -> URLSession {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.httpCookieStorage = nil
        cfg.httpShouldSetCookies = false
        cfg.urlCache = nil
        cfg.urlCredentialStorage = nil
        cfg.timeoutIntervalForRequest = 3600     // our own clocks below; a quiet help is no error
        cfg.waitsForConnectivity = false
        return URLSession(configuration: cfg)
    }

    var running: Bool { ws != nil && !stopped }

    /// Läuft bis zum Ende der Hilfe; gibt den Satz für das Fenster zurück (leer: einfach schließen).
    func run() async -> String {
        guard let url = ziel.socket else { return Texte.t("name_falsch") }
        let ws = session.webSocketTask(with: url)
        ws.maximumMessageSize = Ereignisse.maxMessage
        self.ws = ws
        ws.resume()
        defer { session.finishTasksAndInvalidate() }
        Task { @MainActor [weak self] in              // no answer within 20 s: give up
            try? await Task.sleep(nanoseconds: Self.wait)
            if let self, !self.greeted { self.ws?.cancel(with: .goingAway, reason: nil) }
        }
        do {
            try await send(["typ": "hallo", "schluessel": ziel.key, "art": "mac"])
            guard let h = try await receiveJSON(), h["typ"] as? String == "stand", h["stand"] as? String == "frage" else {
                greeted = true
                stop()
                return Texte.t("neu_laden")
            }
            greeted = true
            helper = Ereignisse.plain(h["admin"] as? String ?? "", max: Self.helperMax)   // erst jetzt: Schlüssel angenommen
            if helper.isEmpty { helper = "Admin" }
            let r = ViewAlert.ask(message: Texte.t("frage", helper: helper, host: ziel.shown),
                                  info: Texte.t("frage_mehr"),
                                  buttons: [Texte.t("ablehnen"), Texte.t("ansehen"), Texte.t("erlauben")],
                                  timeout: 60, countdown: Texte.raw("countdown"))
            if stopped { return "" }
            var answer = r == 2 ? "control" : r == 1 ? "view" : "no"
            var note = ""
            if answer == "control" && !AXIsProcessTrusted() {          // without Accessibility: view only, said once
                answer = "view"
                note = Texte.t("nur_ansehen_jetzt")
            }
            try await send(["typ": "antwort", "modus": answer])
            if answer == "no" {
                stop()
                return Texte.t("abgelehnt")
            }
            mode = answer
            marks = ViewMarks(display: display, text: barText(), end: Texte.t("beenden")) { [weak self] in
                self?.quiet = true
                self?.stop { NSApp.terminate(nil) }
            }
            if note.isEmpty { status.hide() } else { status.say(note) }
            frames = Task { @MainActor [weak self] in await self?.frameLoop() }
            let why = await receiveLoop()
            stop()
            return quiet ? "" : why
        } catch {
            let early = mode.isEmpty && !stopped
            stop()
            return quiet ? "" : early && !greeted ? Texte.t("keine_verbindung", host: ziel.shown) : Texte.t("beendet")
        }
    }

    /// Alles hier zu (Fenster geschlossen, „Beenden“, Ende der Hilfe); sagt dem Panel noch „ende“.
    func stop(then: (() -> Void)? = nil) {
        guard !stopped else {
            then?()
            return
        }
        stopped = true
        steuern = false
        frames?.cancel()
        marks?.close()
        marks = nil
        guard let ws else {
            then?()
            return
        }
        let bye = Data(#"{"typ":"ende"}"#.utf8)
        ws.send(.string(String(decoding: bye, as: UTF8.self))) { _ in
            ws.cancel(with: .normalClosure, reason: nil)
            if let then { DispatchQueue.main.async(execute: then) }
        }
    }

    private func barText() -> String {
        steuern ? Texte.t("leiste_aktiv", helper: helper)
            : mode == "control" ? Texte.t("leiste_erlaubt", helper: helper) : Texte.t("leiste_ansehen", helper: helper)
    }

    private func send(_ m: [String: String]) async throws {
        guard let ws else { throw URLError(.cancelled) }
        let d = try JSONSerialization.data(withJSONObject: m)
        try await ws.send(.string(String(decoding: d, as: UTF8.self)))
    }

    /// the next JSON object from the panel; nil when it closed or sent something too big
    private func receiveJSON() async throws -> [String: Any]? {
        guard let ws else { return nil }
        while true {
            switch try await ws.receive() {
            case .string(let s):
                guard s.utf8.count <= Ereignisse.maxMessage else { return nil }     // zu groß: das ist nicht das Panel
                if let d = try? JSONSerialization.jsonObject(with: Data(s.utf8)) as? [String: Any] { return d }
            case .data:
                continue                                                            // vom Panel kommen keine Bilder
            @unknown default:
                continue
            }
        }
    }

    /// Nachrichten vom Panel bis zum Ende; gibt den Satz für das Fenster zurück.
    private func receiveLoop() async -> String {
        while !stopped {
            guard let m = try? await receiveJSON() else { return Texte.t("beendet") }
            switch m["typ"] as? String {
            case "modus":
                let an = mode == "control" && (m["steuern"] as? Bool) == true
                if an != steuern {
                    steuern = an
                    marks?.say(barText())
                }
            case "eingabe" where mode == "control" && steuern:
                for e in Ereignisse.clean(m) {
                    if !steuern || stopped { break }
                    ViewInput.apply(e, display: display)
                }
            case "stand" where m["stand"] as? String == "zu", "fehler":
                return Texte.t("beendet")
            default:
                continue
            }
        }
        return Texte.t("beendet")
    }

    /// Das Bild des Hauptbildschirms, höchstens viermal je Sekunde; ein zu großes wird kleiner gerechnet.
    private func frameLoop() async {
        var last: Data?
        var sent = Date.distantPast
        while !Task.isCancelled && !stopped {
            let shot = await Task.detached(priority: .userInitiated) { () -> Data? in
                if let a = ViewShot.take(), a.data.count <= Ereignisse.maxFrame { return a.data }
                if let b = ViewShot.take(side: 1280, quality: 0.4), b.data.count <= Ereignisse.maxFrame { return b.data }
                return nil
            }.value
            if stopped { return }
            if let shot, shot != last || Date().timeIntervalSince(sent) > Self.keepAlive {
                do {
                    try await ws?.send(.data(shot))
                    last = shot
                    sent = Date()
                } catch {
                    return
                }
            }
            try? await Task.sleep(nanoseconds: ViewKeys.frameGap)
        }
    }
}
