import SwiftUI

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
    @StateObject private var talk = Conversation()
    @State private var typed = ""
    @State private var settings = false
    @Environment(\.scenePhase) private var scene

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { scroll in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 10) {
                            if talk.messages.isEmpty {
                                Text("Frag mich etwas, zum Beispiel: „Wie wird das Wetter morgen?“")
                                    .foregroundStyle(.secondary)
                                    .padding(.top, 40)
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
                }
                VStack(spacing: 8) {
                    MicButton(phase: talk.phase, level: talk.level) { talk.tap() }
                    Text(talk.status).font(.footnote).foregroundStyle(.secondary)
                    HStack {
                        TextField("Oder schreiben …", text: $typed)
                            .textFieldStyle(.roundedBorder)
                            .submitLabel(.send)
                            .onSubmit(send)
                        Button(action: send) { Image(systemName: "paperplane.fill") }
                            .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                .padding()
            }
            .navigationTitle("Spark")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { talk.restart() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Neues Gespräch")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { settings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Einstellungen")
                }
            }
            .sheet(isPresented: $settings) { SettingsView() }
            .task { await app.refresh() }
            .onChange(of: scene) {
                // leaving the app while it listens: no recording in the background
                if scene != .active && talk.phase == .listening { talk.stop() }
            }
        }
    }

    private func send() {
        talk.write(typed)
        typed = ""
    }
}

struct Bubble: View {
    let message: Conversation.Message

    var body: some View {
        let mine = message.role == "user"
        HStack {
            if mine { Spacer(minLength: 40) }
            Text(message.text.isEmpty ? "…" : message.text)
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
        .accessibilityLabel(phase == .idle ? "Sprechen" : "Anhalten")
    }

    private var icon: String {
        switch phase {
        case .idle: return "mic.fill"
        case .listening: return "stop.fill"
        case .transcribing, .thinking: return "ellipsis"
        case .speaking: return "speaker.wave.2.fill"
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject var app: AppState
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
                    Text("„Hey Siri, Frag Spark“ fragt den Spark auch ohne die App zu öffnen, auch mit AirPods und im Auto.")
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
