import AppKit
import SwiftUI

/// Frag Spark: a question as text (or spoken, when Diktieren is on), the answer as plain, selectable text.
/// The Spark keeps follow-ups in context itself.
@MainActor
final class AskController: ObservableObject {
    static let shared = AskController()
    static let windowID = "ask"

    struct Entry: Identifiable {
        let id = UUID()
        let question: String
        let answer: String
        let failed: Bool
    }

    @Published var input = ""
    @Published private(set) var entries: [Entry] = []
    @Published private(set) var busy = false
    @Published private(set) var status = ""
    /// the question on its way (shown as a bubble until the answer is there)
    @Published private(set) var pending: String?

    private var task: Task<Void, Never>?

    static func open() {
        let c = shared
        Dictation.shared.onAskText = { [weak c] text in
            guard let c else { return }
            c.input = c.input.isEmpty ? text : c.input + " " + text
        }
        Windows.shared.show(windowID, title: "Frag Spark", size: NSSize(width: 520, height: 520)) {
            AskView(c: c, dictation: Dictation.shared, model: AppModel.shared)
        }
        Windows.shared.whenClosed(windowID) {
            if Dictation.shared.recording && Dictation.shared.forAsk { Dictation.shared.discard() }
        }
    }

    func send() {
        let q = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !busy else { return }
        guard q.count <= SparkClient.askMax else {
            status = "Die Frage ist zu lang (höchstens \(SparkClient.askMax) Zeichen)."
            return
        }
        guard let client = AppModel.shared.client else {
            status = "Nicht gekoppelt."
            return
        }
        busy = true
        pending = q
        status = ""
        task = Task { @MainActor [weak self] in
            do {
                let a = try await client.ask(q)
                guard let self else { return }
                self.entries.append(Entry(question: q, answer: a.trimmingCharacters(in: .whitespacesAndNewlines), failed: false))
                self.input = ""
                self.status = ""
            } catch is CancellationError {
                self?.status = ""
            } catch {
                let msg = AppModel.shared.absorb(error)
                self?.status = msg
            }
            self?.pending = nil
            self?.busy = false
        }
    }

    func copyLast() {
        guard let a = entries.last(where: { !$0.failed })?.answer, !a.isEmpty else { return }
        Clip.put(a)
        status = "Antwort kopiert."
    }

    func clear() {
        task?.cancel()
        entries = []
        pending = nil
        status = ""
    }
}

struct AskView: View {
    @ObservedObject var c: AskController
    @ObservedObject var dictation: Dictation
    @ObservedObject var model: AppModel

    private static let bottomID = "unten"

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 10) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            if c.entries.isEmpty && c.pending == nil {
                                HStack(spacing: 10) {
                                    FaceView(size: 30)
                                    Text(verbatim: "Frag den Spark etwas. Folgefragen kennen den Zusammenhang.")
                                        .foregroundColor(Theme.muted)
                                }
                                .padding(.top, 4)
                            }
                            ForEach(c.entries) { e in
                                own(e.question)
                                answer(e.answer)
                            }
                            if let q = c.pending {
                                own(q)
                                HStack(alignment: .top, spacing: 8) {
                                    FaceView(size: 30)
                                    HStack(spacing: 8) {
                                        ProgressView().controlSize(.small)
                                        Text(verbatim: "Spark denkt nach …")
                                            .foregroundColor(Theme.muted)
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(BubbleShape(topLeft: 14, topRight: 14, bottomRight: 14, bottomLeft: 4)
                                        .fill(Theme.soft))
                                    .overlay(BubbleShape(topLeft: 14, topRight: 14, bottomRight: 14, bottomLeft: 4)
                                        .stroke(Theme.line, lineWidth: 1))
                                }
                            }
                            Color.clear.frame(height: 1).id(Self.bottomID)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 4)
                    }
                    .onChange(of: c.entries.count) { _ in
                        withAnimation { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                    }
                    .onChange(of: c.pending) { _ in
                        withAnimation { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                    }
                }

                HStack(alignment: .bottom, spacing: 8) {
                    TextField(c.entries.isEmpty ? "Frag den Spark …" : "Frag weiter …", text: $c.input, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .lineLimit(1...5)
                        .onSubmit { c.send() }
                        .disabled(c.busy)
                        .padding(.vertical, 8)
                    if model.part("dictate") {
                        Button {
                            Dictation.shared.toggle(.ask)
                        } label: {
                            Image(systemName: micActive ? "stop.fill" : "mic")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(micActive ? Theme.bad : Theme.accent)
                                .frame(width: 32, height: 32)
                                .background(Circle().fill(Theme.soft))
                                .overlay(Circle().stroke(Theme.line, lineWidth: 1))
                                .contentShape(Circle())
                        }
                        .buttonStyle(.plain)
                        .help(Text(verbatim: dictation.recording ? "Aufnahme beenden" : "Frage sprechen"))
                        .accessibilityLabel(Text(verbatim: dictation.recording ? "Aufnahme beenden" : "Frage sprechen"))
                        .disabled(c.busy || dictation.working || (dictation.recording && !dictation.forAsk))
                    }
                    Button("Senden") { c.send() }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(c.busy || c.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .padding(.bottom, 2)
                }
                .padding(.leading, 12)
                .padding(.trailing, 6)
                .padding(.vertical, 4)
                .background(RoundedRectangle(cornerRadius: 12).fill(Theme.card))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1))

                HStack(spacing: 8) {
                    if dictation.working {
                        ProgressView().controlSize(.small)
                    }
                    Text(verbatim: c.status)
                        .font(.system(size: 12))
                        .foregroundColor(Theme.muted)
                        .lineLimit(3)
                        .textSelection(.enabled)
                    Spacer()
                    Button("Neu") { c.clear() }
                        .buttonStyle(SoftButtonStyle())
                        .disabled(c.entries.isEmpty && c.pending == nil)
                    Button("Kopieren") { c.copyLast() }
                        .buttonStyle(SoftButtonStyle())
                        .disabled(c.entries.isEmpty)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .frame(minWidth: 420, minHeight: 380)
    }

    private var micActive: Bool {
        dictation.recording && dictation.forAsk
    }

    /// the person's question: right, gradient
    private func own(_ q: String) -> some View {
        HStack {
            Spacer(minLength: 60)
            Text(verbatim: q)
                .font(.system(size: 13))
                .foregroundColor(.white)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(BubbleShape(topLeft: 14, topRight: 14, bottomRight: 4, bottomLeft: 14).fill(Theme.diagonal))
        }
    }

    /// the Spark's answer: left, soft card with the face
    private func answer(_ a: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            FaceView(size: 30)
            Text(verbatim: a)
                .font(.system(size: 13))
                .foregroundColor(Theme.fg)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(BubbleShape(topLeft: 14, topRight: 14, bottomRight: 14, bottomLeft: 4).fill(Theme.soft))
                .overlay(BubbleShape(topLeft: 14, topRight: 14, bottomRight: 14, bottomLeft: 4)
                    .stroke(Theme.line, lineWidth: 1))
            Spacer(minLength: 30)
        }
    }
}
