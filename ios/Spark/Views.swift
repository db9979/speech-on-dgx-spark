import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        Group {
            if app.paired { ChatView() } else { PairView() }
        }
        .alert(item: $app.offered) { link in
            Alert(title: Text("Mit diesem Spark koppeln?"),
                  message: Text("\(link.base.host ?? "")\n\nNur koppeln, wenn das dein eigener Spark ist."),
                  primaryButton: .default(Text("Koppeln")) { Task { await app.pair(link) } },
                  secondaryButton: .cancel(Text("Abbrechen")))
        }
    }
}

struct PairView: View {
    @EnvironmentObject var app: AppState
    @State private var pasted = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Diese App spricht mit deinem Spark. Zum Koppeln im Panel unter Ich → iPhone-App auf „iPhone koppeln“ tippen.")
                    Text("Am PC: den QR-Code mit der Kamera dieses iPhones scannen. Auf diesem iPhone: dort „in der App öffnen“ antippen.")
                        .foregroundStyle(.secondary)
                }
                Section("Oder den Link hier einfügen") {
                    TextField("spark-app://pair?…", text: $pasted, axis: .vertical)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Koppeln") {
                        if let url = URL(string: pasted.trimmingCharacters(in: .whitespacesAndNewlines)) { app.open(url) }
                    }
                    .disabled(pasted.isEmpty || app.busy)
                }
                if app.busy {
                    Section { ProgressView("Kopple …") }
                }
                if let m = app.message {
                    Section { Text(m).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Spark koppeln")
        }
    }
}

struct ChatView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var talk = Conversation.shared
    @State private var typed = ""
    @State private var settings = false
    @State private var history = false
    @State private var camera = false
    @State private var files = false
    @State private var photo: PhotosPickerItem?
    @Environment(\.scenePhase) private var scene

    var body: some View {
        NavigationStack {
            Group {
                if talk.standing { StandView() } else { talking }
            }
            .navigationTitle("Spark")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { talk.restart() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Neues Gespräch")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { history = true } label: { Image(systemName: "clock.arrow.circlepath") }
                        .accessibilityLabel("Verlauf")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { settings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Einstellungen")
                }
            }
            .sheet(isPresented: $settings, onDismiss: { talk.settingsChanged() }) { SettingsView() }
            .sheet(isPresented: $history) { HistoryView() }
            .fullScreenCover(isPresented: $camera) {
                CameraPicker { image in
                    camera = false
                    if let image { read { try await Reader.photo(image, name: String(localized: "Foto")) } }
                }
                .ignoresSafeArea()
            }
            .fileImporter(isPresented: $files, allowedContentTypes: [.pdf, .plainText, .text, .image]) { result in
                if case .success(let url) = result { read { try await Reader.file(url) } }
            }
            .onChange(of: photo) {
                guard let item = photo else { return }
                photo = nil
                read {
                    guard let data = try await item.loadTransferable(type: Data.self), let image = UIImage(data: data) else {
                        throw SparkError(message: String(localized: "Das Foto kann ich nicht laden."))
                    }
                    return try await Reader.photo(image, name: String(localized: "Foto"))
                }
            }
            .task { await talk.begin(await app.refresh()) }
            .onChange(of: scene) { talk.scene(scene) }
            .onChange(of: talk.standing, initial: true) { UIApplication.shared.isIdleTimerDisabled = talk.standing }
            .alert(talk.offer?.question ?? "", isPresented: Binding(get: { talk.offer != nil }, set: { if !$0 { talk.offer = nil } })) {
                Button("Ja") { if let o = talk.offer { talk.offer = nil; PhoneAction.run(o) } }
                Button("Nein", role: .cancel) { talk.offer = nil }
            } message: {
                Text("Du kannst auch „Ja“ oder „Nein“ sagen.")
            }
        }
        .environmentObject(talk)
    }

    private var talking: some View {
        VStack(spacing: 0) {
            if talk.unreachable { OfflineBanner() }
            FaceView(mood: talk.mood, mic: talk.level, out: { talk.audio.outLevel }, kind: talk.allowed.face)
                .frame(maxHeight: talk.messages.isEmpty ? 260 : 130)
                .padding(.top, 8)
                .onTapGesture { talk.tap() }
                .animation(.easeInOut(duration: 0.3), value: talk.messages.isEmpty)
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        if talk.messages.isEmpty {
                            Text("Frag mich etwas, zum Beispiel: „Wie wird das Wetter morgen?“")
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: .infinity)
                        }
                        ForEach(talk.messages) { m in
                            Bubble(message: m).id(m.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: talk.messages.last?.text) {
                    if let id = talk.messages.last?.id { withAnimation { scroll.scrollTo(id, anchor: .bottom) } }
                }
            }
            if let e = talk.error {
                Text(e).font(.footnote).foregroundStyle(.red).padding(.horizontal)
            } else if let n = talk.notice {
                Text(n).font(.footnote).foregroundStyle(.secondary).padding(.horizontal)
            }
            VStack(spacing: 8) {
                MicButton(phase: talk.phase, level: talk.level) { talk.tap() }
                Text(talk.status).font(.footnote).foregroundStyle(.secondary)
                if talk.reading {
                    ProgressView("Lese den Text …").font(.footnote)
                } else if let a = talk.attachment {
                    AttachmentChip(attachment: a, remove: { talk.attachment = nil },
                                   store: talk.allowed.docs && !talk.stored ? { Task { await talk.storeAttachment() } } : nil,
                                   storing: talk.storing)
                }
                HStack {
                    Menu {
                        if UIImagePickerController.isSourceTypeAvailable(.camera) {
                            Button { camera = true } label: { Label("Foto aufnehmen", systemImage: "camera") }
                        }
                        PhotosPicker(selection: $photo, matching: .images) { Label("Foto auswählen", systemImage: "photo") }
                        Button { files = true } label: { Label("Dokument", systemImage: "doc") }
                    } label: {
                        Image(systemName: "paperclip")
                    }
                    .accessibilityLabel("Foto oder Dokument anhängen")
                    .disabled(talk.reading)
                    TextField(talk.attachment == nil ? LocalizedStringKey("Oder schreiben …") : LocalizedStringKey("Frage zum Anhang …"), text: $typed)
                        .textFieldStyle(.roundedBorder)
                        .submitLabel(.send)
                        .onSubmit(send)
                    Button(action: send) { Image(systemName: "paperplane.fill") }
                        .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .padding()
        }
    }

    private func send() {
        talk.write(typed)
        typed = ""
    }

    /// Reads the text on the iPhone; only that text goes along with the next questions.
    private func read(_ work: @escaping () async throws -> Attachment) {
        talk.reading = true
        Task {
            do { talk.attach(try await work()) } catch { talk.error = error.localizedDescription }
            talk.reading = false
        }
    }
}

/// The Spark cannot be reached: say so plainly, show what waits, try again.
struct OfflineBanner: View {
    @EnvironmentObject var talk: Conversation

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Spark nicht erreichbar", systemImage: "wifi.exclamationmark").font(.subheadline.bold())
            if talk.outbox.isEmpty {
                Text("Geschriebene Fragen gehen raus, sobald er wieder da ist.").font(.footnote)
            } else {
                Text("Wartende Fragen: \(talk.outbox.count). Sie gehen raus, sobald er wieder da ist.").font(.footnote)
            }
            HStack {
                Button("Erneut versuchen") { Task { await talk.check() } }
                if !talk.outbox.isEmpty {
                    Spacer()
                    Button("Wartende löschen", role: .destructive) { talk.dropOutbox() }
                }
            }
            .font(.footnote)
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.orange.opacity(0.18))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
        .padding(.top, 6)
    }
}

struct AttachmentChip: View {
    let attachment: Attachment
    let remove: () -> Void
    /// nil: storing is not allowed (panel switch) or already done
    let store: (() -> Void)?
    let storing: Bool

    var body: some View {
        VStack(spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: attachment.kind == "photo" ? "photo" : "doc.text")
                Text(verbatim: attachment.name).lineLimit(1)
                Text("\(attachment.text.count) Zeichen").foregroundStyle(.secondary)
                Button(action: remove) { Image(systemName: "xmark.circle.fill") }
                    .accessibilityLabel("Anhang entfernen")
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Color(.secondarySystemBackground))
            .clipShape(Capsule())
            if storing {
                ProgressView()
            } else if let store {
                Button(action: store) { Label("In „Meine Dokumente“ speichern", systemImage: "tray.and.arrow.down") }
                    .buttonStyle(.bordered)
            }
        }
        .font(.footnote)
    }
}

/// Earlier conversations of this profile (the same list as the panel's Protokoll). Tapping one continues it.
struct HistoryView: View {
    @EnvironmentObject var talk: Conversation
    @Environment(\.dismiss) private var dismiss
    @State private var list: [SavedConvo] = []
    @State private var loading = true
    @State private var failed: String?
    @State private var search = ""

    private var shown: [SavedConvo] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return list }
        return list.filter { c in
            c.title.lowercased().contains(q) || c.msgs.contains { ($0["content"] as? String)?.lowercased().contains(q) == true }
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView()
                } else if let failed {
                    ContentUnavailableView("Verlauf nicht geladen", systemImage: "wifi.exclamationmark", description: Text(failed))
                } else if list.isEmpty {
                    ContentUnavailableView("Noch keine Gespräche", systemImage: "clock")
                } else {
                    List(shown) { c in
                        Button {
                            talk.resume(c)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(c.title.isEmpty ? String(localized: "Gespräch") : c.title).lineLimit(1)
                                Text(c.updated, format: .dateTime.day().month().hour().minute())
                                    .font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                        .foregroundStyle(.primary)
                    }
                    .searchable(text: $search)
                }
            }
            .navigationTitle("Verlauf")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .task {
                do { list = try await SparkAPI.current?.convos() ?? [] } catch { failed = error.localizedDescription }
                loading = false
            }
        }
    }
}

/// On the charger: big face, the clock and the last answer, like a small speaker on the shelf.
/// The screen stays on; at night it is dimmed.
struct StandView: View {
    @EnvironmentObject var talk: Conversation

    var body: some View {
        TimelineView(.everyMinute) { tl in
            let hour = Calendar.current.component(.hour, from: tl.date)
            let night = hour >= 22 || hour < 7
            VStack(spacing: 16) {
                Text(tl.date, format: .dateTime.hour().minute())
                    .font(.system(size: 64, weight: .light, design: .rounded))
                    .monospacedDigit()
                Text(tl.date, format: .dateTime.weekday(.wide).day().month(.wide))
                    .foregroundStyle(.secondary)
                FaceView(mood: talk.mood, mic: talk.level, out: { talk.audio.outLevel }, kind: talk.allowed.face)
                    .frame(maxWidth: 320)
                    .onTapGesture { talk.tap() }
                if let last = talk.messages.last(where: { $0.role == "assistant" }), !last.text.isEmpty {
                    Text(last.text)
                        .font(.title3)
                        .multilineTextAlignment(.center)
                        .lineLimit(4)
                        .padding(.horizontal)
                }
                Text(talk.error ?? talk.status).font(.footnote).foregroundStyle(talk.error == nil ? Color.secondary : Color.red)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
            .foregroundStyle(.white)
            .opacity(night && talk.phase == .waiting ? 0.35 : 1)
            .environment(\.colorScheme, .dark)
        }
    }
}

struct Bubble: View {
    let message: Conversation.Message

    var body: some View {
        let mine = message.role == "user"
        HStack {
            if mine { Spacer(minLength: 40) }
            VStack(alignment: .leading, spacing: 4) {
                if let label = message.label { Text(verbatim: label).font(.footnote).opacity(0.85) }
                Text(verbatim: message.text.isEmpty ? "…" : message.text)
            }
                .textSelection(.enabled)
                .padding(10)
                .background(mine ? Color.accentColor.opacity(0.85) : Color(.secondarySystemBackground))
                .foregroundStyle(mine ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            if !mine { Spacer(minLength: 40) }
        }
    }
}

struct MicButton: View {
    let phase: Conversation.Phase
    let level: Float
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                Circle()
                    .fill(phase == .listening ? Color.red : Color.accentColor)
                    .frame(width: 84, height: 84)
                    .scaleEffect(1 + CGFloat(level) * 0.25)
                    .animation(.easeOut(duration: 0.1), value: level)
                Image(systemName: icon).font(.system(size: 34, weight: .semibold)).foregroundStyle(.white)
            }
        }
        .accessibilityLabel(phase == .idle || phase == .waiting ? "Sprechen" : "Anhalten")
    }

    private var icon: String {
        switch phase {
        case .idle: return "mic.fill"
        case .waiting: return "ear"
        case .listening: return "stop.fill"
        case .transcribing, .thinking: return "ellipsis"
        case .speaking: return "speaker.wave.2.fill"
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var talk: Conversation
    @AppStorage("handsFree") private var handsFree = false
    @AppStorage("bargeIn") private var bargeIn = true
    @AppStorage("wake") private var wake = false
    @AppStorage("wakeWord") private var wakeWord: WakeWord.Word = .spark
    @AppStorage("stand") private var stand = false
    @AppStorage("batteryMinutes") private var batteryMinutes = 30
    @AppStorage("speakNotes") private var speakNotes = true
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Gekoppelt") {
                    LabeledContent("Profil", value: app.profile)
                    LabeledContent("Spark", value: Store.baseURL?.host ?? "")
                }
                Section {
                    NavigationLink("Mein Profil") { ProfileView() }
                } footer: {
                    Text("Stimme, Antworten und „Von selbst“ wie im Panel.")
                }
                Section {
                    Toggle("Freihändig", isOn: $handsFree)
                    Toggle("Ins Wort fallen", isOn: $bargeIn)
                } header: { Text("Gespräch") } footer: {
                    Text("Freihändig: nach jeder Antwort hört die App wieder zu, bis 8 Sekunden lang nichts kommt. Ins Wort fallen: einfach losreden hält die Antwort an.")
                }
                Section {
                    Toggle("Weckwort", isOn: $wake).disabled(!talk.allowed.listen)
                    Picker("Wort", selection: $wakeWord) {
                        ForEach(WakeWord.Word.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .disabled(!wake || !talk.allowed.listen)
                    Picker("Am Akku", selection: $batteryMinutes) {
                        Text("Nur am Ladekabel").tag(0)
                        Text("30 Minuten").tag(30)
                        Text("1 Stunde").tag(60)
                        Text("3 Stunden").tag(180)
                    }
                    .disabled(!wake || !talk.allowed.listen)
                    Toggle("Ständer-Modus am Ladekabel", isOn: $stand)
                } header: { Text("Dauerhaft zuhören") } footer: {
                    if talk.allowed.listen {
                        Text("Das Weckwort erkennt das iPhone selbst, ohne Internet. Erst danach geht etwas an deinen Spark. Am Akku hört es nach der letzten Nutzung nur so lange zu wie eingestellt.")
                    } else {
                        Text("Im Panel unter Ich → iPhone-App „Dauerhaft zuhören erlauben“ einschalten.")
                    }
                }
                Section {
                    Toggle("Von selbst sprechen", isOn: $speakNotes).disabled(!talk.allowed.proactive)
                } footer: {
                    if talk.allowed.proactive {
                        Text("Hinweise, die der Spark von selbst gibt (Morgenrunde, Erinnerungen), sagt die App laut, solange sie offen ist.")
                    } else {
                        Text("Dafür im Panel „Von selbst“ für dein Profil einschalten.")
                    }
                }
                Section {
                    Text("„Hey Siri, Frag Spark“ fragt den Spark auch ohne die App zu öffnen, auch mit AirPods und im Auto.")
                    Text("Schnellstart: In den iPhone-Einstellungen unter Action-Button → Kurzbefehl „Spark zuhören“ wählen. Dasselbe gibt es im Kontrollzentrum und als Widget für den Sperrbildschirm.")
                        .foregroundStyle(.secondary)
                    Text("Was die App darf, stellst du im Panel unter Ich → iPhone-App ein. Dort entfernst du das iPhone auch, wenn es verloren geht.")
                        .foregroundStyle(.secondary)
                }
                Section {
                    Button("Entkoppeln", role: .destructive) { confirm = true }
                }
                Section {
                    LabeledContent("App", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
                }
            }
            .navigationTitle("Einstellungen")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .confirmationDialog("Schlüssel von diesem iPhone löschen?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Entkoppeln", role: .destructive) {
                    app.unpair()
                    dismiss()
                }
            } message: {
                Text("Im Panel unter Ich → iPhone-App das iPhone auch entfernen, dann gilt der Schlüssel nirgends mehr.")
            }
        }
    }
}
