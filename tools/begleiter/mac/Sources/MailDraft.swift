import AppKit
import Carbon
import SwiftUI

/// Part "mail" (⌥⌘M, "Antwort entwerfen"): the selected mail of Apple Mail is read locally through AppleScript, the
/// Spark writes an answer (/api/write/assist art "antwort"), and Mail opens a NEW reply window with it. Nothing is
/// ever sent. In Outlook (no usable AppleScript in the new Outlook) the answer goes to the clipboard.
///
/// Untrusted text (the Spark's answer) never becomes script source: the script is a fixed constant and the text
/// travels as a parameter of a handler call (an Apple event with a string descriptor).
@MainActor
enum MailDraft {
    static let windowID = "mail"
    static let mailBundle = "com.apple.mail"
    static let outlookBundle = "com.microsoft.outlook"
    static let maxMail = 20000

    static func start(front: NSRunningApplication?) {
        let model = AppModel.shared
        guard model.paired else {
            Windows.showPairing()
            return
        }
        guard model.part("mail") else {
            HUD.show(AppModel.offHint("Antwort entwerfen"))
            return
        }
        let bundle = front?.bundleIdentifier?.lowercased() ?? ""
        if bundle == outlookBundle {
            Task { await startOutlook() }
            return
        }
        guard !NSRunningApplication.runningApplications(withBundleIdentifier: mailBundle).isEmpty else {
            HUD.show("Erst in Mail eine Mail auswählen, dann ⌥⌘M.", symbol: "envelope")
            return
        }
        switch MailScript.readSelected() {
        case .failure(let e):
            show(e)
        case .success(let m):
            guard m.id != 0 else {
                HUD.show("In Mail ist keine Mail ausgewählt.", symbol: "envelope")
                return
            }
            MailBox.show(MailBox(kind: .mail(id: m.id), from: m.sender, subject: m.subject, mail: m.content))
        }
    }

    /// Outlook: the marked text of the mail (⌘C, with Accessibility) or pasted by hand; the answer to the clipboard.
    private static func startOutlook() async {
        var text = ""
        if Access.trusted {
            text = await Clip.copySelection() ?? ""
        }
        MailBox.show(MailBox(kind: .outlook, from: "", subject: "", mail: text))
    }

    static func show(_ e: MailScript.Failure) {
        switch e {
        case .notAllowed:
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert()
            a.messageText = "Der Begleiter darf Mail nicht steuern"
            a.informativeText = """
                Für „Antwort entwerfen“ liest der Begleiter die ausgewählte Mail und öffnet einen Antwortentwurf. \
                Erlauben unter Systemeinstellungen → Datenschutz & Sicherheit → Automation → Spark-Begleiter → Mail.
                """
            a.addButton(withTitle: "Systemeinstellungen öffnen")
            a.addButton(withTitle: "Abbrechen")
            if a.runModal() == .alertFirstButtonReturn,
               let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
                NSWorkspace.shared.open(url)
            }
        case .other(let m):
            HUD.show(m, symbol: "exclamationmark.triangle", seconds: 6)
        }
    }
}

/// The fixed AppleScript and its two handlers.
@MainActor
enum MailScript {
    enum Failure: Error {
        case notAllowed
        case other(String)
    }

    struct Message {
        let sender: String
        let subject: String
        let content: String
        let id: Int32
    }

    private static let source = """
        on pickSelection()
        \ttell application "Mail"
        \t\tset sel to {}
        \t\ttry
        \t\t\tset sel to selected messages of message viewer 1
        \t\tend try
        \t\tif sel is missing value or sel is {} then set sel to selection
        \t\treturn sel
        \tend tell
        end pickSelection

        on readSelected()
        \tset sel to pickSelection()
        \tif sel is missing value or sel is {} then return {"", "", "", 0}
        \ttell application "Mail"
        \t\tset m to item 1 of sel
        \t\tset s to sender of m
        \t\tif s is missing value then set s to ""
        \t\tset t to subject of m
        \t\tif t is missing value then set t to ""
        \t\tset c to content of m
        \t\tif c is missing value then set c to ""
        \t\treturn {s as text, t as text, c as text, id of m}
        \tend tell
        end readSelected

        on makeReply(answerText, wantedId)
        \tset sel to pickSelection()
        \tif sel is missing value then set sel to {}
        \ttell application "Mail"
        \t\tset m to missing value
        \t\trepeat with x in sel
        \t\t\tif (id of x) is wantedId then set m to contents of x
        \t\tend repeat
        \t\tif m is missing value then error "Die Mail ist in Mail nicht mehr ausgewählt." number 1001
        \t\tset r to reply m with opening window
        \t\tdelay 0.3
        \t\tset oldContent to content of r
        \t\tif oldContent is missing value then set oldContent to ""
        \t\tset content of r to answerText & return & oldContent
        \t\tactivate
        \tend tell
        \treturn "ok"
        end makeReply
        """

    private static var compiled: NSAppleScript?

    private static func script() -> Result<NSAppleScript, Failure> {
        if let compiled { return .success(compiled) }
        guard let s = NSAppleScript(source: source) else { return .failure(.other("Das Mail-Skript fehlt.")) }
        var err: NSDictionary?
        guard s.compileAndReturnError(&err) else {
            return .failure(.other("Das Mail-Skript ließ sich nicht übersetzen."))
        }
        compiled = s
        return .success(s)
    }

    // FourCCs: 'ascr' / 'psbr' (call a handler), 'snam' (its name), '----' (the parameters)
    private static let suite: AEEventClass = 0x6173_6372
    private static let subroutine: AEEventID = 0x7073_6272
    private static let nameKey: AEKeyword = 0x736e_616d
    private static let directKey: AEKeyword = 0x2d2d_2d2d

    /// Calls a handler of the fixed script; the parameters are descriptors, never source text.
    private static func call(_ handler: String, _ params: [NSAppleEventDescriptor]) -> Result<NSAppleEventDescriptor, Failure> {
        let s: NSAppleScript
        switch script() {
        case .failure(let f): return .failure(f)
        case .success(let x): s = x
        }
        let event = NSAppleEventDescriptor.appleEvent(withEventClass: suite, eventID: subroutine,
                                                      targetDescriptor: NSAppleEventDescriptor.currentProcess(),
                                                      returnID: AEReturnID(kAutoGenerateReturnID),
                                                      transactionID: AETransactionID(kAnyTransactionID))
        event.setParam(NSAppleEventDescriptor(string: handler.lowercased()), forKeyword: nameKey)
        let list = NSAppleEventDescriptor.list()
        for (i, p) in params.enumerated() {
            list.insert(p, at: i + 1)
        }
        event.setParam(list, forKeyword: directKey)
        var err: NSDictionary?
        let result = s.executeAppleEvent(event, error: &err)
        if let err {
            let n = (err[NSAppleScript.errorNumber] as? NSNumber)?.intValue ?? 0
            if n == -1743 || n == -10004 { return .failure(.notAllowed) }
            if n == -600 { return .failure(.other("Mail läuft nicht.")) }
            if n == 1001 { return .failure(.other("Die Mail ist in Mail nicht mehr ausgewählt.")) }
            if n == -128 { return .failure(.other("Abgebrochen.")) }
            return .failure(.other("Mail hat nicht geantwortet (Fehler \(n))."))
        }
        return .success(result)
    }

    static func readSelected() -> Result<Message, Failure> {
        switch call("readSelected", []) {
        case .failure(let f):
            return .failure(f)
        case .success(let d):
            guard d.numberOfItems >= 4 else { return .success(Message(sender: "", subject: "", content: "", id: 0)) }
            let sender = d.atIndex(1)?.stringValue ?? ""
            let subject = d.atIndex(2)?.stringValue ?? ""
            let content = d.atIndex(3)?.stringValue ?? ""
            let id = d.atIndex(4)?.int32Value ?? 0
            return .success(Message(sender: String(sender.prefix(300)), subject: String(subject.prefix(500)),
                                    content: String(content.prefix(MailDraft.maxMail)), id: id))
        }
    }

    /// Opens Mail's reply window for the message `id` with `answer` above the quoted mail. Never sends.
    static func makeReply(answer: String, id: Int32) -> Failure? {
        switch call("makeReply", [NSAppleEventDescriptor(string: answer), NSAppleEventDescriptor(int32: id)]) {
        case .failure(let f): return f
        case .success: return nil
        }
    }
}

/// The small window: which mail, optional notes, "Entwurf schreiben".
@MainActor
final class MailBox: ObservableObject {
    enum Kind {
        case mail(id: Int32)
        case outlook
    }

    let kind: Kind
    let from: String
    let subject: String
    @Published var mail: String
    @Published var notes = ""
    @Published private(set) var busy = false
    @Published private(set) var status = ""
    @Published private(set) var isError = false
    private var task: Task<Void, Never>?

    init(kind: Kind, from: String, subject: String, mail: String) {
        self.kind = kind
        self.from = from
        self.subject = subject
        self.mail = mail
    }

    var isOutlook: Bool {
        if case .outlook = kind { return true }
        return false
    }

    static func show(_ box: MailBox) {
        Windows.shared.close(MailDraft.windowID)
        Windows.shared.show(MailDraft.windowID, title: "Antwort entwerfen", size: NSSize(width: 520, height: 470),
                            floating: true) {
            MailBoxView(box: box)
        }
        Windows.shared.whenClosed(MailDraft.windowID) { [weak box] in box?.task?.cancel() }
    }

    /// what the Spark gets as "mail": sender and subject (when known) and the text, at most 20000 characters
    private var mailText: String {
        var head = ""
        if !from.isEmpty { head += "Von: \(from)\n" }
        if !subject.isEmpty { head += "Betreff: \(subject)\n" }
        if !head.isEmpty { head += "\n" }
        return String((head + mail).prefix(MailDraft.maxMail))
    }

    func write() {
        guard !busy else { return }
        guard !mail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            setStatus(isOutlook ? "Bitte den Text der Mail einfügen." : "Die Mail ist leer.", error: true)
            return
        }
        guard let client = AppModel.shared.client else {
            setStatus("Nicht gekoppelt.", error: true)
            return
        }
        let model = AppModel.shared
        let app = model.part("context") ? (isOutlook ? "outlook" : "mail") : nil
        let notes = String(self.notes.trimmingCharacters(in: .whitespacesAndNewlines).prefix(2000))
        let body = mailText
        let kind = self.kind
        busy = true
        setStatus("Spark schreibt die Antwort …", error: false)
        task = Task { @MainActor [weak self] in
            do {
                let r = try await client.improve(text: notes, art: "antwort", sprache: nil, wunsch: "", app: app, mail: body)
                let answer = r.text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !answer.isEmpty else {
                    self?.busy = false
                    self?.setStatus("Der Spark hat keine Antwort geschrieben.", error: true)
                    return
                }
                switch kind {
                case .outlook:
                    Clip.put(answer)
                    Windows.shared.close(MailDraft.windowID)
                    HUD.show("Antwortentwurf in der Zwischenablage. In die Antwort einfügen (⌘V).",
                             symbol: "doc.on.clipboard", seconds: 8)
                case .mail(let id):
                    if let f = MailScript.makeReply(answer: answer, id: id) {
                        Clip.put(answer)
                        self?.busy = false
                        switch f {
                        case .notAllowed:
                            self?.setStatus("Keine Freigabe für Mail. Der Entwurf liegt in der Zwischenablage.", error: true)
                            MailDraft.show(f)
                        case .other(let m):
                            self?.setStatus(m + " Der Entwurf liegt in der Zwischenablage.", error: true)
                        }
                        return
                    }
                    Windows.shared.close(MailDraft.windowID)
                    HUD.show("Antwortentwurf in Mail geöffnet – nichts gesendet.", symbol: "envelope", seconds: 5)
                }
            } catch is CancellationError {
                self?.busy = false
            } catch {
                self?.busy = false
                self?.setStatus(AppModel.shared.absorb(error), error: true)
            }
        }
    }

    private func setStatus(_ s: String, error: Bool) {
        status = s
        isError = error
    }
}

struct MailBoxView: View {
    @ObservedObject var box: MailBox

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    FaceView(size: 28)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(verbatim: "Antwort entwerfen")
                            .font(.system(size: 14, weight: .semibold))
                        Text(verbatim: box.isOutlook ? "für Outlook · Ergebnis in die Zwischenablage" : "in Mail · wird nie gesendet")
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                    }
                    Spacer()
                }
                if box.isOutlook {
                    caption("Text der Mail (markieren und ⌥⌘M, oder hier einfügen)")
                    TextEditor(text: $box.mail)
                        .font(.system(size: 12))
                        .frame(minHeight: 110)
                        .padding(6)
                        .padding(.trailing, 30)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                        .overlay(alignment: .bottomTrailing) {
                            FieldMic(id: "mail.text", label: "Mail-Text", disabled: box.busy) { t in
                                box.mail = Dictation.append(t, to: box.mail, max: MailDraft.maxMail)
                            }
                            .padding(5)
                        }
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(verbatim: "Von: " + box.from)
                            .font(.system(size: 12))
                            .lineLimit(1)
                        Text(verbatim: "Betreff: " + box.subject)
                            .font(.system(size: 12, weight: .semibold))
                            .lineLimit(2)
                        Text(verbatim: DeskConfig.plain(box.mail, max: 240))
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                            .lineLimit(3)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Theme.soft))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                }
                caption("Was soll drinstehen? (freiwillig, z. B. „zusagen, Termin Dienstag 10 Uhr“)")
                HStack(alignment: .bottom, spacing: 6) {
                    TextField("Stichpunkte für die Antwort …", text: $box.notes, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .lineLimit(2...5)
                        .disabled(box.busy)
                    FieldMic(id: "mail.notes", label: "Stichpunkte", disabled: box.busy) { t in
                        box.notes = Dictation.append(t, to: box.notes, max: 2000)
                    }
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                HStack(spacing: 8) {
                    if box.busy { ProgressView().controlSize(.small) }
                    Text(Wege.text(box.status))
                        .font(.system(size: 12))
                        .foregroundColor(box.isError ? Theme.bad : Theme.muted)
                        .lineLimit(3)
                        .textSelection(.enabled)
                    Spacer()
                    Button("Abbrechen") { Windows.shared.close(MailDraft.windowID) }
                        .buttonStyle(SoftButtonStyle())
                        .keyboardShortcut(.cancelAction)
                    Button("Entwurf schreiben") { box.write() }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(box.busy)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 440, minHeight: 380)
    }

    private func caption(_ s: String) -> some View {
        Text(verbatim: s)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(Theme.muted)
    }
}
