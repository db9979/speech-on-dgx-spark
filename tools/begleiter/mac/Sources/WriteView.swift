import AppKit
import SwiftUI

/// Schreibhilfe window: choose what should happen, see the changes (removed red and struck through, added green),
/// edit the result, take it over.
@MainActor
final class WriteController: ObservableObject {
    enum Target {
        case hotkey(NSRunningApplication?)   // paste into that program
        case menu                            // result to the clipboard
        case service                         // "Mit Spark verbessern": result back to the Services call
    }

    static let windowID = "write"
    static let translate = "uebersetzen"

    @Published var source: String
    @Published var art: String
    @Published var sprache: String
    @Published var wunsch: String
    @Published var result = ""
    @Published private(set) var diff: AttributedString?
    @Published private(set) var noDiff = false
    @Published private(set) var status = ""
    @Published private(set) var isError = false
    @Published private(set) var busy = false
    @Published private(set) var ready = false

    let target: Target
    let arts: [ArtInfo]
    let langs: [LangInfo]
    let preview: Bool
    /// part "context": the front app's category ("mail", "browser", …), nil when off or unknown
    let app: String?
    /// called once with the text to take over, or nil when cancelled
    var finish: ((String?) -> Void)?

    private var lead = ""
    private var trail = ""
    private var task: Task<Void, Never>?
    private var finished = false

    init(text: String, target: Target, config: DeskConfig, app: String? = nil) {
        self.source = text
        self.target = target
        self.app = app
        self.arts = config.offeredArts
        self.langs = config.langs
        self.preview = config.preview
        self.art = config.offeredArts.contains(where: { $0.id == config.writeArt }) ? config.writeArt
            : (config.offeredArts.first?.id ?? "korrigieren")
        self.sprache = config.langs.contains(where: { $0.id == config.writeSprache }) ? config.writeSprache
            : (config.langs.first?.id ?? "en")
        self.wunsch = config.writeWunsch
    }

    /// "aus Outlook" (where the text came from)
    var sourceLabel: String {
        switch target {
        case .menu: return ""
        case .service: return "aus dem Dienste-Menü"
        case .hotkey(let app):
            let name = DeskConfig.plain(app?.localizedName ?? "", max: 40)
            return name.isEmpty ? "" : "aus " + name
        }
    }

    var applyTitle: String {
        switch target {
        case .menu: return "In die Zwischenablage"
        case .hotkey(let app): return (app == nil || !Access.trusted) ? "In die Zwischenablage" : "Übernehmen"
        case .service: return "Übernehmen"
        }
    }

    // ------------------------------------------------------------------ opening

    /// The window for the hotkey and the menu.
    static func open(text: String, target: Target, config: DeskConfig, app: String? = nil) {
        Windows.shared.close(windowID)
        let c = WriteController(text: text, target: target, config: config, app: app)
        c.finish = { result in
            Windows.shared.close(windowID)
            guard let result else { return }
            Task { @MainActor in
                if case .hotkey(let app) = target, app != nil, Access.trusted {
                    _ = await Clip.paste(result, into: app)
                } else {
                    Clip.put(result)
                    HUD.show("Text ist in der Zwischenablage (⌘V fügt ihn ein).", symbol: "doc.on.clipboard")
                }
            }
        }
        Windows.shared.show(windowID, title: "Spark Schreibhilfe", size: NSSize(width: 620, height: 600), floating: true) {
            WriteView(c: c)
        }
        Windows.shared.whenClosed(windowID) { [weak c] in c?.closed() }
        c.begin()
    }

    /// For "Mit Spark verbessern": runs the window modally and gives the text to put back (nil = leave as is).
    static func runForService(text: String, config: DeskConfig, app: String? = nil) -> String? {
        let id = "service"
        let c = WriteController(text: text, target: .service, config: config, app: app)
        var out: String?
        c.finish = { result in
            out = result
            Windows.stopModal()
            Windows.shared.close(id)
        }
        let w = Windows.shared.show(id, title: "Mit Spark verbessern", size: NSSize(width: 620, height: 600), floating: true) {
            WriteView(c: c)
        }
        Windows.shared.whenClosed(id) { [weak c] in
            c?.closed()
            Windows.stopModal()
        }
        c.begin()
        NSApp.runModal(for: w)
        return out
    }

    // ------------------------------------------------------------------ actions

    func begin() {
        if source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            setStatus("Text eingeben oder einfügen, dann „Neu“.", error: false)
        } else {
            run()
        }
    }

    static func split(_ full: String) -> (lead: String, core: String, trail: String) {
        let core = full.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !core.isEmpty, let r = full.range(of: core) else { return ("", core, "") }
        return (String(full[..<r.lowerBound]), core, String(full[r.upperBound...]))
    }

    func run() {
        guard !busy else { return }
        let parts = Self.split(source)
        guard !parts.core.isEmpty else {
            setStatus("Bitte zuerst Text eingeben.", error: true)
            return
        }
        guard parts.core.count <= SparkClient.writeMax else {
            setStatus("Der Text ist zu lang (höchstens \(SparkClient.writeMax) Zeichen).", error: true)
            return
        }
        guard let client = AppModel.shared.client else {
            setStatus("Nicht gekoppelt.", error: true)
            return
        }
        lead = parts.lead
        trail = parts.trail
        busy = true
        ready = false
        setStatus("Spark arbeitet …", error: false)
        let art = self.art
        let sprache = art == Self.translate ? self.sprache : nil
        let wunsch = self.wunsch
        let app = AppModel.shared.part("context") ? self.app : nil
        task = Task { @MainActor [weak self] in
            do {
                let r = try await client.improve(text: parts.core, art: art, sprache: sprache, wunsch: wunsch, app: app)
                self?.show(r)
            } catch is CancellationError {
                self?.busy = false
            } catch {
                let msg = AppModel.shared.absorb(error)
                self?.busy = false
                self?.setStatus(msg, error: true)
            }
        }
    }

    private func show(_ r: WriteOutcome) {
        busy = false
        result = r.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let d = r.diff {
            diff = Self.render(d)
            noDiff = false
        } else {
            diff = nil
            noDiff = true
        }
        var s = Self.changesText(r)
        if let ms = r.ms {
            if s.hasSuffix(".") { s.removeLast() }
            s += " · " + String(format: "%.1f s", Double(ms) / 1000).replacingOccurrences(of: ".", with: ",")
        }
        setStatus(s, error: false)
        ready = true
        if !preview, case .service = target {
            apply()
        }
    }

    static func changesText(_ r: WriteOutcome) -> String {
        guard r.diff != nil, let n = r.changes else { return "Fertig." }
        switch n {
        case 0: return "Keine Änderungen nötig."
        case 1: return "1 Änderung."
        default: return "\(n) Änderungen."
        }
    }

    func apply() {
        guard ready, !finished else { return }
        let core = result.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !core.isEmpty else {
            setStatus("Das Ergebnis ist leer.", error: true)
            return
        }
        finished = true
        finish?(lead + core + trail)
    }

    func copy() {
        let core = result.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !core.isEmpty else { return }
        Clip.put(core)
        setStatus("Kopiert.", error: false)
    }

    func cancel() {
        task?.cancel()
        guard !finished else { return }
        finished = true
        finish?(nil)
    }

    /// the window was closed with its close button
    func closed() {
        task?.cancel()
        if !finished {
            finished = true
            if case .service = target { finish?(nil) }
        }
    }

    private func setStatus(_ s: String, error: Bool) {
        status = s
        isError = error
    }

    // ------------------------------------------------------------------ the changes, as plain text with colours

    static let removedColor = Theme.delFg
    static let removedBack = Theme.del
    static let addedColor = Theme.insFg
    static let addedBack = Theme.ins

    static func render(_ diff: [(op: String, text: String)]) -> AttributedString {
        var out = AttributedString()
        for p in diff {
            var a = AttributedString(p.text)
            switch p.op {
            case "-":
                a[AttributeScopes.SwiftUIAttributes.ForegroundColorAttribute.self] = removedColor
                a[AttributeScopes.SwiftUIAttributes.BackgroundColorAttribute.self] = removedBack
                a[AttributeScopes.SwiftUIAttributes.StrikethroughStyleAttribute.self] =
                    Text.LineStyle(pattern: .solid, color: removedColor)
            case "+":
                a[AttributeScopes.SwiftUIAttributes.ForegroundColorAttribute.self] = addedColor
                a[AttributeScopes.SwiftUIAttributes.BackgroundColorAttribute.self] = addedBack
            default:
                break
            }
            out.append(a)
        }
        return out
    }
}

struct WriteView: View {
    @ObservedObject var c: WriteController

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    FaceView(size: 28)
                    Text(verbatim: "Text verbessern")
                        .font(.system(size: 14, weight: .semibold))
                    Spacer()
                    if !c.sourceLabel.isEmpty {
                        Text(verbatim: c.sourceLabel)
                            .font(.system(size: 12))
                            .foregroundColor(Theme.muted)
                            .lineLimit(1)
                    }
                }

                FlowLayout(spacing: 6) {
                    ForEach(c.arts) { a in
                        ChipButton(title: a.de, selected: c.art == a.id) {
                            guard c.art != a.id else { return }
                            c.art = a.id
                            if !c.busy && !c.source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { c.run() }
                        }
                        .disabled(c.busy)
                    }
                }

                HStack(spacing: 8) {
                    if c.art == WriteController.translate {
                        Picker("Sprache", selection: $c.sprache) {
                            ForEach(c.langs) { l in
                                Text(verbatim: l.de).tag(l.id)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 140)
                    }
                    TextField("Wunsch (optional)", text: $c.wunsch)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { c.run() }
                    Button("Neu") { c.run() }
                        .buttonStyle(SoftButtonStyle())
                        .disabled(c.busy)
                }

                caption("Dein Text")
                editor($c.source, minHeight: 64)

                caption("Änderungen")
                ScrollView {
                    Group {
                        if let d = c.diff {
                            Text(d)
                                .foregroundColor(Theme.fg)
                        } else if c.noDiff {
                            Text(verbatim: "(Bei dieser Art gibt es keine Markierung der Änderungen.)")
                                .italic()
                                .foregroundColor(Theme.muted)
                        } else if c.busy {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text(verbatim: "Spark arbeitet …").foregroundColor(Theme.muted)
                            }
                        } else {
                            Text(verbatim: "")
                        }
                    }
                    .font(.system(size: 13))
                    .lineSpacing(3)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                }
                .frame(minHeight: 90)
                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.soft))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))

                caption("Ergebnis (änderbar)")
                editor($c.result, minHeight: 64)

                HStack(spacing: 8) {
                    if c.busy {
                        ProgressView().controlSize(.small)
                    }
                    Text(Wege.text(c.status))
                        .font(.system(size: 12))
                        .foregroundColor(c.isError ? Theme.bad : Theme.muted)
                        .lineLimit(3)
                        .textSelection(.enabled)
                    Spacer()
                    Button("Abbrechen") { c.cancel() }
                        .buttonStyle(SoftButtonStyle())
                        .keyboardShortcut(.cancelAction)
                    Button("Kopieren") { c.copy() }
                        .buttonStyle(SoftButtonStyle())
                        .disabled(!c.ready)
                    Button(c.applyTitle) { c.apply() }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(!c.ready)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .frame(minWidth: 520, minHeight: 500)
    }

    private func caption(_ s: String) -> some View {
        Text(verbatim: s)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(Theme.muted)
    }

    private func editor(_ text: Binding<String>, minHeight: CGFloat) -> some View {
        TextEditor(text: text)
            .font(.system(size: 13))
            .scrollContentBackground(.hidden)
            .padding(6)
            .frame(minHeight: minHeight)
            .background(RoundedRectangle(cornerRadius: 10).fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
    }
}
