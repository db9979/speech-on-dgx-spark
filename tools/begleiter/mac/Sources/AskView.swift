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
        status = "Spark denkt nach …"
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
        status = ""
    }
}

struct AskView: View {
    @ObservedObject var c: AskController
    @ObservedObject var dictation: Dictation
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if c.entries.isEmpty {
                            Text(verbatim: "Frag den Spark etwas. Folgefragen kennen den Zusammenhang.")
                                .foregroundColor(.secondary)
                        }
                        ForEach(c.entries) { e in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(verbatim: e.question)
                                    .font(.body.weight(.semibold))
                                    .textSelection(.enabled)
                                Text(verbatim: e.answer)
                                    .textSelection(.enabled)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .id(e.id)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                }
                .background(Color(nsColor: .textBackgroundColor))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.3)))
                .onChange(of: c.entries.count) { _ in
                    if let last = c.entries.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }

            HStack(alignment: .bottom, spacing: 8) {
                TextField("Frage", text: $c.input, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { c.send() }
                    .disabled(c.busy)
                if model.part("dictate") {
                    Button {
                        Dictation.shared.toggle(.ask)
                    } label: {
                        Image(systemName: dictation.recording && dictation.forAsk ? "stop.circle.fill" : "mic")
                            .foregroundColor(dictation.recording && dictation.forAsk ? .red : .primary)
                    }
                    .help(Text(verbatim: dictation.recording ? "Aufnahme beenden" : "Frage sprechen"))
                    .disabled(c.busy || dictation.working || (dictation.recording && !dictation.forAsk))
                }
                Button("Senden") { c.send() }
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(c.busy || c.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            HStack(spacing: 8) {
                if c.busy || dictation.working {
                    ProgressView().controlSize(.small)
                }
                Text(verbatim: c.status)
                    .foregroundColor(.secondary)
                    .lineLimit(3)
                    .textSelection(.enabled)
                Spacer()
                Button("Neu") { c.clear() }
                    .disabled(c.entries.isEmpty)
                Button("Kopieren") { c.copyLast() }
                    .disabled(c.entries.isEmpty)
            }
        }
        .padding(12)
        .frame(minWidth: 420, minHeight: 360)
    }
}
