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

    /// the note the next question answers (button "Antworten" without text): sent as "note"
    @Published private(set) var noteContext: (n: Int, title: String)?

    private var task: Task<Void, Never>?
    private var generation = 0
    /// the text in the field came (at least partly) from the mic button: the question counts as spoken
    private var inputSpoken = false

    static func open() {
        let c = shared
        Dictation.shared.onAskText = { [weak c] text in
            guard let c else { return }
            c.input = c.input.isEmpty ? text : c.input + " " + text
            c.inputSpoken = true
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
        let note = noteContext?.n
        let spoken = inputSpoken
        inputSpoken = false
        Speaker.shared.stop()                 // a new question ends the reading aloud
        generation += 1
        let mine = generation
        busy = true
        pending = q
        status = ""
        task = Task { @MainActor [weak self] in
            do {
                let a = try await client.ask(q, note: note)
                guard let self else { return }
                self.noteContext = nil
                let clean = a.trimmingCharacters(in: .whitespacesAndNewlines)
                self.entries.append(Entry(question: q, answer: clean, failed: false))
                Self.speakIfWanted(clean, spoken: spoken)
                if self.generation == mine {
                    self.input = ""
                    self.status = ""
                }
            } catch is CancellationError {
                if self?.generation == mine { self?.status = "" }
            } catch {
                let msg = AppModel.shared.absorb(error)
                if self?.generation == mine { self?.status = msg }
            }
            guard let self, self.generation == mine else { return }
            self.pending = nil
            self.busy = false
        }
    }

    /// Work of another part (a file, the screen, the wake word, a reply to a note) whose answer belongs in this
    /// window: the label as own bubble, the answer as the Spark's. `notify`: also as a notification.
    func run(question label: String, notify: Bool = false, spoken: Bool = false,
             work: @escaping (SparkClient) async throws -> String) {
        if busy { task?.cancel() }
        task = Task { @MainActor [weak self] in
            await self?.perform(question: label, notify: notify, spoken: spoken, work: work)
        }
    }

    /// "Antworten vorlesen" (part speak): immer | nur bei gesprochenen Fragen | nie
    static func speakIfWanted(_ answer: String, spoken: Bool) {
        let model = AppModel.shared
        guard AskSpeak.wanted(mode: UserDefaults.standard.string(forKey: AskSpeak.key), spoken: spoken,
                              speakOn: model.part("speak")), !answer.isEmpty else { return }
        Speaker.shared.read(answer)
    }

    /// The same, awaited (several files one after the other).
    func perform(question label: String, notify: Bool = false, spoken: Bool = false,
                 work: (SparkClient) async throws -> String) async {
        Self.open()
        Speaker.shared.stop()                 // a new question ends the reading aloud
        guard let client = AppModel.shared.client else {
            status = "Nicht gekoppelt."
            return
        }
        generation += 1
        let mine = generation
        busy = true
        pending = label
        status = ""
        var answer: String?
        var problem = ""
        do {
            answer = try await work(client).trimmingCharacters(in: .whitespacesAndNewlines)
        } catch is CancellationError {
            problem = ""
        } catch {
            problem = AppModel.shared.absorb(error)
        }
        if let answer {
            entries.append(Entry(question: label, answer: answer, failed: false))
            Self.speakIfWanted(answer, spoken: spoken)
            if notify { Notifier.plain(title: "Spark", body: answer) }
        } else if notify && !problem.isEmpty {
            Notifier.plain(title: "Spark", body: problem)
        }
        guard generation == mine else { return }   // a newer piece of work took over
        status = problem
        pending = nil
        busy = false
    }

    /// "Antworten" without text: the window with the note as quoted context; the next question carries it.
    static func openForNote(_ n: Int?, title: String, body: String) {
        let c = shared
        open()
        if let n {
            c.noteContext = (n, DeskConfig.plain(title, max: 80))
            let quote = DeskConfig.plain(body, max: 300)
            c.status = "Antwort auf die Meldung „\(DeskConfig.plain(title, max: 80))“" + (quote.isEmpty ? "" : ": " + quote)
        }
    }

    func copyLast() {
        guard let a = entries.last(where: { !$0.failed })?.answer, !a.isEmpty else { return }
        Clip.put(a)
        status = "Antwort kopiert."
    }

    func clear() {
        task?.cancel()
        inputSpoken = false
        Speaker.shared.stop()
        noteContext = nil
        entries = []
        pending = nil
        status = ""
    }
}

struct AskView: View {
    @ObservedObject var c: AskController
    @ObservedObject var dictation: Dictation
    @ObservedObject var model: AppModel
    @ObservedObject var speaker = Speaker.shared
    @AppStorage(AskSpeak.key) private var speakMode = "voice"

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
                    if model.part("speak") {
                        if speaker.active {
                            Button("Stopp") { speaker.stop() }
                                .buttonStyle(SoftButtonStyle())
                        }
                        Menu {
                            Picker("Antworten vorlesen", selection: $speakMode) {
                                ForEach(AskSpeak.ids, id: \.self) { m in
                                    Text(verbatim: AskSpeak.title(m)).tag(m)
                                }
                            }
                            .pickerStyle(.inline)
                        } label: {
                            Image(systemName: AskSpeak.mode(speakMode) == "never" ? "speaker.slash" : "speaker.wave.2")
                        }
                        .menuStyle(.borderlessButton)
                        .fixedSize()
                        .help(Text(verbatim: "Antworten vorlesen: " + AskSpeak.title(speakMode)))
                        .accessibilityLabel(Text(verbatim: "Antworten vorlesen"))
                    }
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
