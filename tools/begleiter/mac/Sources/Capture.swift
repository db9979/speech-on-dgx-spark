import AppKit
import SwiftUI

/// Part "capture" (Begleiter nachziehen 4a/8a): Schnell erfassen with ⌃⌥N, the tile "Erfassen" or the menu. One line like
/// "Zahnarzt Fr 10 Uhr bei Dr. Weber" or "Milch, Eier auf Einkauf"; the Spark reads it by fixed rules (POST /api/desk/capture) and shows what it
/// found as chips. Saved only with "Eintragen" (the Spark reads the same line again), then "Rückgängig" for 10 minutes;
/// the window closes 12 seconds after. Marked text comes along as the line.
@MainActor
final class CaptureController: ObservableObject {
    static let shared = CaptureController()
    static let windowID = "capture"
    static let maxText = 200

    @Published var line = "" { didSet { if line != oldValue { later() } } }
    @Published private(set) var kind = ""
    @Published private(set) var kinds: [String] = []
    @Published private(set) var chips = "Termin oder Erinnerung, mit Tag, Uhrzeit und Ort."
    @Published private(set) var error = false
    @Published private(set) var result = ""
    @Published private(set) var undo: String?
    @Published private(set) var busy = false
    @Published var focusTick = 0

    private var seq = 0
    private var wait: Task<Void, Never>?
    private var closer: Task<Void, Never>?

    static func open(fromHotkey: Bool) {
        guard AppModel.shared.paired, AppModel.shared.part("capture") else {
            return HUD.show(AppModel.offHint("Schnell erfassen"))
        }
        Task { @MainActor in
            let marked = fromHotkey ? (await Clip.copySelection() ?? "") : ""
            let c = shared
            c.reset(DeskConfig.plain(marked, max: maxText))
            Windows.shared.show(windowID, title: "Schnell erfassen", size: NSSize(width: 440, height: 230), floating: true) {
                CaptureView(c: c)
            }
            c.focusTick += 1
        }
    }

    private func reset(_ text: String) {
        closer?.cancel()
        result = ""
        undo = nil
        kind = ""
        kinds = []
        error = false
        chips = "Termin oder Erinnerung, mit Tag, Uhrzeit und Ort."
        line = text
        if !text.isEmpty { Task { await preview() } }
    }

    static func label(_ k: String) -> String {
        k == "erinnerung" ? "Erinnerung" : k == "liste" ? "Liste" : "Termin"
    }

    func pick(_ k: String) {
        kind = k
        Task { await preview() }
    }

    private func later() {
        guard result.isEmpty else { return }
        wait?.cancel()
        wait = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 400_000_000)
            if !Task.isCancelled { await preview() }
        }
    }

    private func body(save: Bool) -> [String: Any] {
        ["text": String(line.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.maxText)), "kind": kind,
         "tz": TimeZone.current.identifier, "save": save]
    }

    func preview() async {
        let text = line.trimmingCharacters(in: .whitespacesAndNewlines)
        seq += 1
        let mine = seq
        guard !text.isEmpty else {
            chips = "Termin oder Erinnerung, mit Tag, Uhrzeit und Ort."
            error = false
            return
        }
        guard let client = AppModel.shared.client else { return }
        do {
            let d = try await client.postJSON("api/desk/capture", body(save: false), timeout: 20)
            guard mine == seq else { return }
            let ks = (d["kinds"] as? [Any] ?? []).compactMap { $0 as? String }.filter { ["termin", "erinnerung", "liste"].contains($0) }
            kinds = ks
            let k = d["kind"] as? String ?? ""
            kind = ks.contains(k) ? k : ks.first ?? ""
            let found = (d["chips"] as? [Any] ?? []).prefix(4).map { PlainText.line($0, max: 80) }.filter { !$0.isEmpty }
            let title = PlainText.line(d["title"], max: 200)
            chips = Self.label(kind) + ": " + title + (found.isEmpty ? "" : " · " + found.joined(separator: " · "))
            error = false
        } catch {
            guard mine == seq else { return }
            chips = AppModel.shared.absorb(error)
            self.error = true
        }
    }

    func save() {
        guard !busy, undo == nil, result.isEmpty, !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let client = AppModel.shared.client else { return }
        busy = true
        Task { @MainActor in
            defer { busy = false }
            do {
                let d = try await client.postJSON("api/desk/capture", body(save: true), timeout: 40)
                let text = DeskConfig.plain(d["text"] as? String ?? "", max: 240)
                result = text.isEmpty ? "Eingetragen." : text
                let u = d["undo"] as? String ?? ""
                undo = (1...40).contains(u.count) ? u : nil
                closeSoon()
                await ListsCenter.shared.refresh()
            } catch {
                chips = AppModel.shared.absorb(error)
                self.error = true
            }
        }
    }

    func takeBack() {
        guard let u = undo, !busy, let client = AppModel.shared.client else { return }
        busy = true
        closer?.cancel()
        Task { @MainActor in
            defer { busy = false }
            do {
                let d = try await client.postJSON("api/desk/capture/undo", ["undo": u], timeout: 30)
                let text = DeskConfig.plain(d["text"] as? String ?? "", max: 240)
                result = text.isEmpty ? "Zurückgenommen." : text
                undo = nil
            } catch {
                result = AppModel.shared.absorb(error)
            }
            closeSoon()
        }
    }

    private func closeSoon() {
        closer?.cancel()
        closer = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 12_000_000_000)
            if !Task.isCancelled { Windows.shared.close(Self.windowID) }
        }
    }
}

struct CaptureView: View {
    @ObservedObject var c: CaptureController
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(verbatim: "Schnell erfassen")
                .font(.system(size: 15, weight: .semibold))
            TextField("z. B. Zahnarzt Fr 10 Uhr bei Dr. Weber", text: $c.line)
                .textFieldStyle(.roundedBorder)
                .focused($focused)
                .disabled(!c.result.isEmpty)
                .onSubmit { c.save() }
            Text(verbatim: c.chips)
                .font(.system(size: 12))
                .foregroundColor(c.error ? Theme.bad : Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
            if c.kinds.count > 1 && c.result.isEmpty {
                HStack(spacing: 6) {
                    ForEach(c.kinds, id: \.self) { k in
                        Button(CaptureController.label(k)) { c.pick(k) }
                            .buttonStyle(SoftButtonStyle())
                            .overlay(RoundedRectangle(cornerRadius: 9).stroke(c.kind == k ? Theme.accent : Color.clear, lineWidth: 2))
                    }
                }
            }
            if !c.result.isEmpty {
                Text(verbatim: c.result)
                    .font(.system(size: 13))
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                Spacer()
                Button(c.result.isEmpty ? "Abbrechen" : "Schließen") { Windows.shared.close(CaptureController.windowID) }
                    .buttonStyle(SoftButtonStyle())
                    .keyboardShortcut(.cancelAction)
                if c.undo != nil {
                    Button("Rückgängig") { c.takeBack() }
                        .buttonStyle(SoftButtonStyle())
                        .disabled(c.busy)
                }
                if c.result.isEmpty {
                    Button("Eintragen") { c.save() }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(c.busy || c.line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .padding(16)
        .frame(width: 440)
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .onChange(of: c.focusTick) { _ in focused = true }
        .onAppear { focused = true }
    }
}
