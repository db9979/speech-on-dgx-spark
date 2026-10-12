import AppKit
import SwiftUI

/// Part "home" (Smart-Home-Knöpfe): the buttons set in the panel for this device (config.home.buttons), with their
/// state from GET /api/desk/home, as the tray panel's section "Zuhause". A press is POST /api/desk/home {"id"};
/// a 403 whose detail starts with "Codewort" asks for the code word in a password box and sends again with it.
/// The code word is never kept.
@MainActor
final class HomeCenter: ObservableObject {
    static let shared = HomeCenter()

    @Published private(set) var buttons: [HomeButton] = []
    @Published private(set) var pressing: String?
    @Published private(set) var problem = ""

    private var active = false
    private var lastLoad: Date?
    private var loading = false

    func apply(on: Bool, configured: [HomeButton]) {
        active = on
        guard on else {
            buttons = []
            problem = ""
            return
        }
        // the panel's list decides which buttons there are; known states stay
        let old = buttons
        buttons = configured.map { b in
            var x = b
            if x.state == nil { x.state = old.first(where: { $0.id == b.id })?.state }
            return x
        }
        refreshSoon(force: true)
    }

    func refreshSoon(force: Bool = false) {
        guard active else { return }
        if !force, let l = lastLoad, Date().timeIntervalSince(l) < 30 { return }
        Task { await refresh() }
    }

    func refresh() async {
        guard active, !loading, let client = AppModel.shared.client else { return }
        loading = true
        defer { loading = false }
        do {
            let list = try await client.homeButtons()
            guard active else { return }
            buttons = list
            lastLoad = Date()
            problem = ""
        } catch is CancellationError {
        } catch {
            problem = AppModel.shared.absorb(error)
        }
    }

    func press(_ b: HomeButton, code: String? = nil) {
        guard active, pressing == nil, let client = AppModel.shared.client else { return }
        pressing = b.id
        problem = ""
        Task { @MainActor in
            defer { self.pressing = nil }
            do {
                let state = try await client.homePress(id: b.id, code: code)
                if let i = self.buttons.firstIndex(where: { $0.id == b.id }) {
                    self.buttons[i].state = state ?? self.buttons[i].state
                }
                if b.kind != "toggle" {
                    HUD.show("„\(b.name)“ ausgelöst.", symbol: "house")
                }
            } catch SparkProblem.off(let m) where HomeButton.wantsCode(m) {
                self.pressing = nil
                CodeWordBox.ask(for: b, message: m)
            } catch is CancellationError {
            } catch {
                let m = AppModel.shared.absorb(error)
                self.problem = m
                HUD.show(m, symbol: "exclamationmark.triangle")
            }
        }
    }
}

// ------------------------------------------------------------------ the code word

@MainActor
final class CodeWordBox: ObservableObject {
    static let windowID = "codewort"

    let button: HomeButton
    let message: String
    @Published var code = ""

    init(button: HomeButton, message: String) {
        self.button = button
        self.message = message
    }

    static func ask(for b: HomeButton, message: String) {
        let box = CodeWordBox(button: b, message: message)
        Windows.shared.close(windowID)
        Windows.shared.show(windowID, title: "Codewort", size: NSSize(width: 380, height: 220), floating: true) {
            CodeWordView(box: box)
        }
    }

    func send() {
        let c = code
        code = ""
        guard !c.isEmpty else { return }
        Windows.shared.close(Self.windowID)
        HomeCenter.shared.press(button, code: c)
    }
}

struct CodeWordView: View {
    @ObservedObject var box: CodeWordBox

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    FaceView(size: 28)
                    Text(verbatim: "„\(box.button.name)“")
                        .font(.system(size: 14, weight: .semibold))
                        .lineLimit(1)
                    Spacer()
                }
                Text(Wege.text(box.message))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                SecureField("Codewort", text: $box.code)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { box.send() }
                HStack {
                    Spacer()
                    Button("Abbrechen") {
                        box.code = ""
                        Windows.shared.close(CodeWordBox.windowID)
                    }
                    .buttonStyle(SoftButtonStyle())
                    .keyboardShortcut(.cancelAction)
                    Button("Senden") { box.send() }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(box.code.isEmpty)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 340, minHeight: 190)
    }
}
