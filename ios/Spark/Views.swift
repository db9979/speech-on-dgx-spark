import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// "1.0 (412)": the version and the build number (the build number is the commit count, set while building).
enum AppInfo {
    static var version: String {
        let i = Bundle.main.infoDictionary
        return "\(i?["CFBundleShortVersionString"] as? String ?? "?") (\(i?["CFBundleVersion"] as? String ?? "?"))"
    }
}

struct ContentView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        Group {
            if app.paired || app.demo || Demo.scene != nil { ChatView() } else { PairView() }
        }
        .alert(item: $app.offered) { link in
            if let old = link.replacing {
                // already paired with another Spark: switching sends every question there from now on
                return Alert(title: Text("Zu einem anderen Spark wechseln?"),
                             message: Text("Diese App ist mit \(old) gekoppelt. Der Link führt zu \(AppState.label(link.base)).\n\nNur wechseln, wenn das dein eigener Spark ist. Danach gehen alle Fragen dorthin."),
                             primaryButton: .destructive(Text("Wechseln")) { Task { await app.pair(link) } },
                             secondaryButton: .cancel(Text("Abbrechen")))
            }
            return Alert(title: Text("Mit diesem Spark koppeln?"),
                         message: Text("\(link.base.host ?? "")\n\nNur koppeln, wenn das dein eigener Spark ist."),
                         primaryButton: .default(Text("Koppeln")) { Task { await app.pair(link) } },
                         secondaryButton: .cancel(Text("Abbrechen")))
        }
        .sheet(item: $app.invited) { link in JoinView(link: link) }
    }
}

/// An invitation from the panel: name and PIN, then the Spark makes the profile and this iPhone's key.
/// Shows which Spark the link leads to first, as with pairing.
struct JoinView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    let link: AppState.Link
    @State private var name = ""
    @State private var pin = ""
    @State private var pin2 = ""
    @State private var pinMin = 6
    @State private var loading = true
    @State private var ready = false
    @State private var problem: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Du bist zum Sprachassistenten auf diesem Spark eingeladen:")
                    Text(verbatim: link.base.host ?? "").font(.headline)
                    Text("Nur weitermachen, wenn du diese Einladung erwartest.").foregroundStyle(.secondary)
                }
                if loading {
                    Section { ProgressView("Einladung wird geprüft …") }
                } else if ready {
                    Section {
                        TextField("Dein Name", text: $name)
                            .textContentType(.username)
                            .autocorrectionDisabled()
                        SecureField("PIN (mindestens \(pinMin) Zeichen)", text: $pin)
                            .textContentType(.newPassword)
                        SecureField("PIN wiederholen", text: $pin2)
                            .textContentType(.newPassword)
                    } footer: {
                        Text("Mit Name und PIN meldest du dich auch im Browser an. Danach führt dich der Spark durch die Einrichtung.")
                    }
                    Section {
                        Button("Profil anlegen") { Task { await go() } }
                            .disabled(app.busy || name.trimmingCharacters(in: .whitespaces).isEmpty || pin.isEmpty)
                    }
                }
                if let p = problem {
                    Section { Text(verbatim: p).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Einladung")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { app.invited = nil; dismiss() }
                }
            }
            .task { await check() }
        }
        .interactiveDismissDisabled(app.busy)
    }

    private func check() async {
        defer { loading = false }
        do {
            let r = try await SparkAPI.invitation(base: link.base, code: link.code)
            if r.pinOnly {
                problem = String(localized: "Diese Einladung setzt eine neue PIN. Bitte im Browser öffnen.")
                return
            }
            name = r.name
            pinMin = r.pinMin
            ready = true
        } catch {
            problem = error.localizedDescription
        }
    }

    private func go() async {
        problem = nil
        guard pin.count >= pinMin else {
            problem = String(localized: "Die PIN braucht mindestens \(pinMin) Zeichen.")
            return
        }
        guard pin == pin2 else {
            problem = String(localized: "Die beiden PINs sind nicht gleich.")
            return
        }
        do {
            try await app.join(link, name: name.trimmingCharacters(in: .whitespaces), pin: pin)
            dismiss()
        } catch {
            problem = error.localizedDescription
        }
    }
}

struct PairView: View {
    @EnvironmentObject var app: AppState
    @State private var pasted = ""
    @State private var address = ""
    @State private var code = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(SparkAPI.way(String(localized: "Diese App spricht mit deinem Spark. Zum Koppeln im Panel unter Ich → iPhone-App auf „iPhone koppeln“ tippen.")))
                    Text("Am PC: den QR-Code mit der Kamera dieses iPhones scannen. Auf diesem iPhone: dort „in der App öffnen“ antippen.")
                        .foregroundStyle(.secondary)
                    Text("Noch kein Profil? Mit einer Einladung vom Admin legst du es hier gleich an: den Einladungs-Link öffnen und „Lieber gleich in der iPhone-App“ antippen.")
                        .foregroundStyle(.secondary)
                }
                Section("Oder den Link hier einfügen") {
                    TextField("spark-app://pair?… / spark-app://join?…", text: $pasted, axis: .vertical)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Koppeln") {
                        if let url = URL(string: pasted.trimmingCharacters(in: .whitespacesAndNewlines)) { app.open(url) }
                    }
                    .disabled(pasted.isEmpty || app.busy)
                }
                // Apple's app review and anyone with a code from the admin (panel: Prüfzugang für die iPhone-App)
                Section {
                    TextField("Adresse, z. B. https://spark.example.de", text: $address)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Prüf-Code, z. B. ABCD-EFGH-JKMN", text: $code)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                    Button("Mit Prüf-Code verbinden") { app.review(address: address, code: code) }
                        .disabled(address.isEmpty || code.isEmpty || app.busy)
                } header: {
                    Text("Mit Prüf-Code verbinden")
                } footer: {
                    Text("Den Code gibt dir der Admin des Spark. Er gilt 14 Tage.")
                }
                Section {
                    Button("Ohne Spark ansehen") { app.startDemo() }
                } footer: {
                    Text("Eine Vorführung mit Beispielen. Nichts verlässt dieses iPhone.")
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
    @State private var settings = false
    @State private var history = false
    @State private var today = false
    @State private var demoProfile = false
    @State private var camera = false
    @State private var files = false
    @State private var photo: PhotosPickerItem?
    @State private var chatsOpen = false
    /// Meine Sachen (ThingsView.swift): documents, made documents, pictures, music and memory in one place
    @State private var things = false
    @StateObject private var chats = ChatsModel()
    @Environment(\.scenePhase) private var scene

    var body: some View {
        NavigationStack {
            Group {
                // the conversation stays in place behind the stand view (plugging in no longer redraws it and loses the scroll)
                ZStack {
                    talking.opacity(talk.standing ? 0 : 1).allowsHitTesting(!talk.standing).accessibilityHidden(talk.standing)
                    if talk.standing { StandView() }
                }
            }
            .navigationTitle("Spark")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if app.demo {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Vorführung beenden") { app.endDemo() }
                    }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { talk.restart() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("Neues Gespräch")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { history = true } label: { Image(systemName: "clock.arrow.circlepath") }
                        .accessibilityLabel("Verlauf")
                }
                if ThingsView.any(talk.allowed) {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { things = true } label: { Image(systemName: "square.grid.2x2") }
                            .accessibilityLabel("Meine Sachen")
                    }
                }
                if chats.state.on {   // Chats (ChatsView.swift): only when the Spark and the profile have them on
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { chatsOpen = true } label: {
                            Image(systemName: chats.unread > 0 ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                                .overlay(alignment: .topTrailing) {
                                    if chats.unread > 0 {
                                        Text(verbatim: chats.unread > 9 ? "9+" : String(chats.unread))
                                            .font(.system(size: 10, weight: .bold)).foregroundStyle(.white)
                                            .padding(3).background(Circle().fill(.red)).offset(x: 8, y: -8)
                                    }
                                }
                        }
                        .accessibilityLabel(chats.unread > 0 ? Text("Chats, \(chats.unread) ungelesen") : Text("Chats"))
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { today = true } label: { Image(systemName: "sun.max") }
                        .accessibilityLabel("Heute")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { settings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Einstellungen")
                }
            }
            .sheet(isPresented: $today) { TodayView() }
            .sheet(isPresented: $settings, onDismiss: { talk.settingsChanged() }) { SettingsView() }
            .sheet(isPresented: $history) { HistoryView() }
            .sheet(isPresented: $things) { ThingsSheet() }
            .sheet(isPresented: $chatsOpen, onDismiss: { Task { await chats.load() } }) { ChatsView() }
            .task {
                guard Demo.scene == nil else { return }
                while !Task.isCancelled {   // the unread count beside the chats button, once a minute
                    await chats.load()
                    try? await Task.sleep(for: .seconds(60))
                }
            }
            .sheet(isPresented: $demoProfile) { NavigationStack { ProfileView() } }
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
            .task {
                if let s = Demo.scene {
                    Demo.fill(talk, s)
                    history = s == "history"
                    demoProfile = s == "profile"
                    return
                }
                // the last state first (Merken.swift): the buttons are there before the Spark answers
                if talk.allowed == Allowed(), let a = Merken.allowed() { talk.allowed = a }
                await talk.begin(await app.refresh())
            }
            .onChange(of: scene) {
                talk.scene(scene)
                // back in front: conversations, chats and settings fetched ahead (at most every 5 minutes, Merken.swift)
                if scene == .active { Task { await Merken.prefetch(chats: chats.state.on) } }
            }
            .onChange(of: talk.standing, initial: true) { UIApplication.shared.isIdleTimerDisabled = talk.standing }
            .alert(talk.offer?.question ?? "", isPresented: Binding(get: { talk.offer != nil }, set: { if !$0 { talk.offer = nil } })) {
                Button("Ja") { if let o = talk.offer { talk.offer = nil; PhoneAction.run(o) } }
                Button("Nein", role: .cancel) { if let o = talk.offer { PhoneAction.decline(o) }; talk.offer = nil }
            } message: {
                Text("Du kannst auch „Ja“ oder „Nein“ sagen.")
            }
        }
        .environmentObject(talk)
    }

    private var talking: some View {
        VStack(spacing: 0) {
            if talk.offlineShown { OfflineBanner().transition(.move(edge: .top).combined(with: .opacity)) }
            if !talk.rooms.isEmpty { RoomBanner() }
            FaceView(mood: talk.mood, mic: talk.level, out: { Demo.out ?? talk.audio.outLevel }, kind: talk.allowed.face, acts: talk.allowed.faceLife ? talk.faceActs : nil)
                .frame(maxHeight: talk.messages.isEmpty ? 260 : 130)
                .padding(.top, 8)
                .onTapGesture { talk.tap() }
                .animation(.easeInOut(duration: 0.3), value: talk.messages.isEmpty)
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        // a tapped notification (mitteilungen.py): the note on top, with the button that fits it
                        if let n = talk.tapped { MitteilungKarte(x: n).id("mitteilung") }
                        if talk.messages.isEmpty && talk.tapped == nil {
                            Text("Frag mich etwas, zum Beispiel: „Wie wird das Wetter morgen?“")
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: .infinity)
                        }
                        ForEach(talk.messages) { m in
                            if m.role != "user", let v = m.vg { VorgangImGespraech(id: v, message: m).id(m.id) } else { Bubble(message: m).id(m.id) }
                            if m.role != "user", let j = m.picJob { PictureCard(job: j) }
                            if m.role != "user", let steps = m.steps, !steps.isEmpty { StepsFold(steps: steps) }
                            if m.role != "user", m.id == talk.messages.last?.id, let kind = m.confirm {
                                if let v = m.confirmVg { VorschlagKarte(id: v, kind: kind) } else { ConfirmCard(kind: kind) }
                            }
                            if m.role != "user", m.id == talk.messages.last?.id, m.confirm == nil, let a = m.answers, !a.isEmpty {
                                AnswersCard(answers: a)
                            }
                            if m.role != "user", m.rateId != nil { RateBar(message: m) }
                            if m.role != "user", m.wbId != nil { WbFileButton(message: m) }
                            if m.role != "user", let q = m.fundQ, talk.allowed.areas.contains("fund") { FundKarte(q: q, id: m.fundId) }
                            if m.role != "user", let mem = m.mem, !mem.isEmpty { GemerktChips(message: m, items: mem) }
                            if m.role != "user", m.id == talk.messages.last?.id, let more = m.more, !more.isEmpty {
                                MoreRow(kind: m.moreKind ?? "", items: more)
                            }
                        }
                    }
                    .padding()
                }
                .onChange(of: talk.messages.last?.text) {
                    if let id = talk.messages.last?.id { withAnimation { scroll.scrollTo(id, anchor: .bottom) } }
                }
                .onChange(of: talk.tapped?.id) {
                    if talk.tapped != nil { withAnimation { scroll.scrollTo("mitteilung", anchor: .top) } }
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
                    ProgressView(Reader.sendPictures ? LocalizedStringKey("Bereite vor …") : LocalizedStringKey("Lese den Text …")).font(.footnote)
                } else if let a = talk.attachment {
                    AttachmentChip(attachment: a, remove: { talk.attachment = nil },
                                   store: talk.allowed.docs && !talk.stored && a.image == nil ? { Task { await talk.storeAttachment() } } : nil,
                                   storing: talk.storing)
                }
                // the line to type in is its own view: a keystroke redraws only it, not the face and every bubble
                // (Dominik 16.10.2026: „das Tippen ist total langsam“)
                Composer(camera: $camera, files: $files, photo: $photo)
                Text(verbatim: AppInfo.version).font(.caption2).foregroundStyle(.tertiary)
            }
            .padding([.horizontal, .top])
            .padding(.bottom, 4)
        }
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

/// The line to type in, the attachment menu and the send button (ChatView). The typed text lives here, so a
/// keystroke redraws only this row and not the conversation above it.
struct Composer: View {
    @EnvironmentObject var talk: Conversation
    @Binding var camera: Bool
    @Binding var files: Bool
    @Binding var photo: PhotosPickerItem?
    @State private var typed = ""
    @State private var gross = false

    var body: some View {
        HStack(alignment: .bottom) {
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
            // grows with the text up to 5 lines, then scrolls; the key makes a new line, the arrow sends (like the panel, feld.js)
            TextField(talk.attachment == nil ? LocalizedStringKey("Oder schreiben …") : LocalizedStringKey("Frage zum Anhang …"), text: $typed, axis: .vertical)
                .lineLimit(1...5)
                .textFieldStyle(.roundedBorder)
                .onChange(of: talk.suggestion) {
                    if let s = talk.suggestion { typed = s; talk.suggestion = nil }
                }
                .overlay(alignment: .topTrailing) {
                    if GrossAnsicht.lang(typed) {
                        Button { gross = true } label: { Image(systemName: "arrow.up.left.and.arrow.down.right").font(.caption) }
                            .padding(6)
                            .accessibilityLabel("Groß bearbeiten")
                    }
                }
            Button(action: send) { Image(systemName: "paperplane.fill") }
                .disabled(typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .padding(.bottom, 6)
        }
        .sheet(isPresented: $gross) {
            GrossAnsicht(text: $typed, title: "Frage bearbeiten", limit: 0) { gross = false; send() }
        }
    }

    private func send() {
        talk.write(typed)
        typed = ""
    }
}

/// The large view for a long text (Dominik 2026-10-19, plan eingabefelder 3a): the whole screen to read and change it.
/// "Fertig" keeps the text in the field, "Senden" sends it (only where the field sends); from 80 % of a limit a counter.
struct GrossAnsicht: View {
    @Binding var text: String
    let title: LocalizedStringKey
    let limit: Int
    var send: (() -> Void)? = nil
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focus: Bool

    /// from 4 lines (or a long single line) the field offers the large view
    static func lang(_ s: String) -> Bool { s.split(separator: "\n", omittingEmptySubsequences: false).count >= 4 || s.count > 140 }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 6) {
                TextEditor(text: $text)
                    .focused($focus)
                    .font(.body)
                    .onChange(of: text) { if limit > 0 && text.count > limit { text = String(text.prefix(limit)) } }
                if limit > 0 && Double(text.count) >= Double(limit) * 0.8 {
                    Text(verbatim: "\(text.count) / \(limit)").font(.caption).foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            .padding(.horizontal)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Fertig") { dismiss() } }
                if let send {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Senden", action: send).bold()
                            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
            .onAppear { focus = true }
        }
    }
}

/// The Spark cannot be reached: say so plainly, show what waits, try again.
struct OfflineBanner: View {
    @EnvironmentObject var talk: Conversation

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Spark nicht erreichbar", systemImage: "wifi.exclamationmark").font(.subheadline.bold())
            if talk.certBad { Text(verbatim: NetWatch.certificateText()).font(.footnote) }
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

/// "● Küche hört zu bis 21:30 · Beenden": a device of the profile is in room mode (only where and until when).
/// Several: one line with the count, tapping shows each with its own "Beenden".
struct RoomBanner: View {
    @EnvironmentObject var talk: Conversation
    @State private var open = false

    var body: some View {
        let rooms = talk.rooms
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Circle().fill(Color.green).frame(width: 9, height: 9)
                if rooms.count == 1, let r = rooms.first {
                    Text("\(RoomLive.listening([r.name])) bis \(r.until, style: .time)").font(.subheadline.bold()).lineLimit(1)
                } else {
                    Button {
                        open.toggle()
                    } label: {
                        Label(RoomLive.listening(rooms.map(\.name)), systemImage: open ? "chevron.up" : "chevron.down")
                            .font(.subheadline.bold()).lineLimit(1)
                    }
                    .buttonStyle(.plain)
                }
                Spacer(minLength: 4)
                Button("Beenden", role: .destructive) { Task { await talk.endRoom(rooms.count == 1 ? rooms.first : nil) } }
                    .font(.footnote)
                    .buttonStyle(.bordered)
                    .accessibilityLabel(rooms.count == 1 ? Text("Raum-Modus beenden") : Text("Raum-Modus überall beenden"))
            }
            if open && rooms.count > 1 {
                ForEach(rooms) { r in
                    HStack {
                        Text("\(RoomLive.label([r.name])) bis \(r.until, style: .time)").font(.footnote).lineLimit(1)
                        Spacer()
                        Button("Beenden") { Task { await talk.endRoom(r) } }.font(.footnote).buttonStyle(.bordered)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.green.opacity(0.16))
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
                if let data = attachment.image, let ui = UIImage(data: data) {
                    // the photo goes to the Spark itself, which looks at it
                    Image(uiImage: ui).resizable().scaledToFill()
                        .frame(width: 22, height: 22).clipShape(RoundedRectangle(cornerRadius: 4))
                    Text(verbatim: attachment.name).lineLimit(1)
                    Text("Der Spark sieht es sich an").foregroundStyle(.secondary)
                } else {
                    Image(systemName: attachment.kind == "photo" ? "photo" : "doc.text")
                    Text(verbatim: attachment.name).lineLimit(1)
                    Text("\(attachment.text.count) Zeichen").foregroundStyle(.secondary)
                }
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
                Button(action: store) { Label("Bei „Meine Sachen“ speichern", systemImage: "tray.and.arrow.down") }
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
    /// the list shown is the one kept last time (Merken.swift), from then
    @State private var keptAt: Date?

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
                if loading && keptAt == nil {
                    List { LadeZeilen() }
                } else if let failed, keptAt == nil {
                    LadeFehler(title: "Verlauf nicht geladen", message: failed) { await load() }
                } else if list.isEmpty {
                    ContentUnavailableView("Noch keine Gespräche", systemImage: "clock")
                } else {
                    List {
                        if let keptAt { StandNote(at: keptAt, loading: loading).listRowSeparator(.hidden) }
                        ForEach(shown) { c in
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
                    }
                    .searchable(text: $search)
                }
            }
            .navigationTitle("Verlauf")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .task {
                if let demo = Demo.convos { list = demo; loading = false; return }
                if let k = Merken.convoList(), !k.list.isEmpty { list = k.list; keptAt = k.at }
                await load()
            }
        }
    }

    private func load() async {
        loading = true
        failed = nil
        do {
            let got = try await Merken.timed("verlauf") { try await SparkAPI.current?.convos() ?? [] }
            list = got
            keptAt = nil
            Merken.keepConvos(got)
        } catch { failed = error.localizedDescription }
        loading = false
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
                FaceView(mood: talk.mood, mic: talk.level, out: { talk.audio.outLevel }, kind: talk.allowed.face, acts: talk.allowed.faceLife ? talk.faceActs : nil)
                    .frame(maxWidth: 320)
                    .onTapGesture { talk.tap() }
                if let last = talk.messages.last(where: { $0.role == "assistant" }), !last.text.isEmpty {
                    Text(AnswerText.styled(last.text))
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

// Answers as formatted text, like the panel's chat (md.js): the model's Markdown as SwiftUI shows it inline
// (bold, italic, `code`, links), headings and list signs as plain lines. Links only for http(s) to a public
// host (no localhost, no .local, no LAN address), every other link stays text. Copy and share get the text
// without the signs. The voice never says them (the Spark cleans what it speaks).
enum AnswerText {
    static func lines(_ s: String) -> String {
        s.components(separatedBy: "\n").compactMap { line -> String? in
            if line.range(of: #"^\s{0,3}(```|~~~)"#, options: .regularExpression) != nil { return nil }
            var l = line
            if let r = l.range(of: #"^\s{0,3}#{1,6}\s+"#, options: .regularExpression) { l.removeSubrange(r) }
            if let r = l.range(of: #"^\s*[-*+]\s+"#, options: .regularExpression) {
                l.replaceSubrange(r, with: String(l[r].prefix(while: { $0 == " " })) + "• ")
            }
            return l
        }.joined(separator: "\n")
    }

    static func linkOK(_ u: URL) -> Bool {
        guard let scheme = u.scheme?.lowercased(), scheme == "http" || scheme == "https", u.user == nil,
              let host = u.host?.lowercased(), host.contains("."), !host.hasSuffix(".local"), !host.hasSuffix(".lan"),
              !host.hasSuffix(".internal"), !host.hasSuffix(".fritz.box"), !host.hasSuffix(".home.arpa"), !host.contains(":")
        else { return false }
        let lan = #"^(127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.)"#
        return host.range(of: lan, options: .regularExpression) == nil
    }

    static func styled(_ s: String) -> AttributedString {
        let src = lines(s)
        guard src.count <= 60000, var a = try? AttributedString(markdown: src, options: AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace)) else { return AttributedString(src) }
        let bad = a.runs.compactMap { run -> Range<AttributedString.Index>? in
            guard let u = run.link else { return nil }
            return linkOK(u) ? nil : run.range
        }
        for r in bad { a[r].link = nil }
        return a
    }

    static func plain(_ s: String) -> String { String(styled(s).characters) }
}

struct Bubble: View {
    let message: Conversation.Message
    private var copyText: String { message.role == "user" ? message.text : AnswerText.plain(message.text) }

    var body: some View {
        let mine = message.role == "user"
        HStack {
            if mine { Spacer(minLength: 40) }
            VStack(alignment: .leading, spacing: 4) {
                if let label = message.label { Text(verbatim: label).font(.footnote).opacity(0.85) }
                if mine || message.text.isEmpty { Text(verbatim: message.text.isEmpty ? "…" : message.text) } else { Text(AnswerText.styled(message.text)) }
            }
                .padding(10)
                .background(mine ? Color.accentColor.opacity(0.85) : Color(.secondarySystemBackground))
                .foregroundStyle(mine ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .contextMenu {
                    if !message.text.isEmpty {
                        Button { UIPasteboard.general.string = copyText } label: { Label("Kopieren", systemImage: "doc.on.doc") }
                        // "Als Notiz teilen": Notes, Mail, Messages ... from the share sheet
                        ShareLink(item: copyText) { Label("Teilen (z. B. als Notiz)", systemImage: "square.and.arrow.up") }
                    }
                }
            if !mine { Spacer(minLength: 40) }
        }
    }
}

/// A picture painted for an answer (Bilder malen, bilder.py): waits while the Spark paints, then shows it;
/// touching and holding saves or shares it. The job leads to the picture also in a conversation opened again.
struct PictureCard: View {
    let job: String
    @State private var image: UIImage?
    @State private var line: LocalizedStringKey = "Malt …"
    @State private var gone = false

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .frame(maxWidth: 420, maxHeight: 420, alignment: .leading)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("Gemaltes Bild")
                    .contextMenu {
                        ShareLink(item: Image(uiImage: image), preview: SharePreview("Bild", image: Image(uiImage: image))) {
                            Label("Sichern oder teilen", systemImage: "square.and.arrow.up")
                        }
                    }
            } else if !gone {
                HStack(spacing: 8) { ProgressView(); Text(line).font(.footnote).foregroundStyle(.secondary) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task(id: job) { await follow() }
    }

    /// Looks every 2.5 s until the picture is there or the job ended without one.
    private func follow() async {
        guard let api = SparkAPI.current else { return }
        while !Task.isCancelled {
            do {
                let j = try await api.pictureJob(job)
                if j.state == "done", let pic = j.pic {
                    image = UIImage(data: try await api.pictureFile(pic))
                    gone = image == nil
                    return
                }
                if j.state == "error" || j.state == "done" { gone = true; return }
                line = j.state == "wait" ? "Wartet auf eine Gesprächspause …" : "Malt …"
            } catch {
                gone = true   // deleted, or the Spark does not paint any more: the answer's text says the rest
                return
            }
            try? await Task.sleep(nanoseconds: 2_500_000_000)
        }
    }
}

/// 👍/👎 under an answer (Einstellungs-Assistent, only when the Spark sent an id for it): 👎 opens five reasons,
/// a short text and „Frage mitschicken“ (off: the case keeps no words of the question).
/// „Das kannst du auch sagen“ (saetze.py): the Spark's sentences under the last answer; a tap puts one into the field.
struct MoreRow: View {
    let kind: String
    let items: [MoreItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(kind == "near" ? LocalizedStringKey("Meintest du:") : kind == "new" ? LocalizedStringKey("Neu bei dir:")
                 : LocalizedStringKey("Das kannst du auch sagen:"))
                .font(.caption).foregroundStyle(.secondary)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(items, id: \.self) { x in
                        Button { Conversation.shared.suggest(x) } label: {
                            Text(verbatim: x.text).font(.footnote).lineLimit(1)
                        }
                        .buttonStyle(.bordered)
                        .clipShape(Capsule())
                    }
                }
            }
        }
        .padding(.leading, 6)
    }
}

/// Ablauf zeigen (ablauf.py): the tools of an answer, folded: „3 Werkzeuge benutzt · 2,1 s“, open: ✓/⚠ name and time.
struct StepsFold: View {
    let steps: [StepItem]

    static func seconds(_ ms: Int) -> String {
        (Double(ms) / 1000).formatted(.number.precision(.fractionLength(0...1))) + " s"
    }

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(steps.enumerated()), id: \.offset) { _, x in
                    Text(verbatim: (x.ok ? "✓ " : "⚠ ") + x.name + " · " + Self.seconds(x.ms))
                        .foregroundStyle(x.ok ? Color.green : Color.orange)
                }
            }
            .font(.caption)
        } label: {
            Text(steps.count == 1 ? String(localized: "1 Werkzeug benutzt") : String(localized: "\(steps.count) Werkzeuge benutzt"))
                + Text(verbatim: " · " + Self.seconds(steps.reduce(0) { $0 + $1.ms }))
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.leading, 6)
    }
}

/// Freigabe-Karte (ablauf.py): a proposal of the last answer waits for "Ja". Ja and Nein send the word like a typed
/// answer; the Spark's module that proposed decides with its own rules, the card carries nothing out.
struct ConfirmCard: View {
    let kind: String
    @State private var sent = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Wartet auf dein Ja: \(kind)").font(.footnote.bold())
            HStack(spacing: 10) {
                Button("Ja") { sent = true; Conversation.shared.write("Ja") }.buttonStyle(.borderedProminent)
                Button("Nein") { sent = true; Conversation.shared.write("Nein") }.buttonStyle(.bordered)
            }
            .disabled(sent)
        }
        .padding(10)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange, lineWidth: 1.5))
    }
}

/// Rückfrage-Karte (ablauf.asks): the answers to the question the answer ends with; a tap sends one like a typed answer
struct AnswersCard: View {
    let answers: [String]
    @State private var sent = false

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Array(answers.enumerated()), id: \.offset) { _, a in
                    Button(a) { sent = true; Conversation.shared.write(a) }.buttonStyle(.bordered)
                }
            }
        }
        .disabled(sent)
    }
}

/// Gemerkt-Hinweis (gemerkt.py): „✓ Gemerkt: …“ under the answer with „Rückgängig“ (only while the fact is unchanged,
/// the Spark checks) and „Ansehen“ (Ich → Gedächtnis in the panel); a conversation drawn again fetches the text.
struct GemerktChips: View {
    let message: Conversation.Message
    let items: [Conversation.Gemerkt]
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.id) { g in
                VStack(alignment: .leading, spacing: 2) {
                    Text(g.text.isEmpty ? String(localized: "Gemerkt") : String(localized: "Gemerkt: \(g.text)"))
                        .foregroundStyle(.secondary)
                    HStack(spacing: 14) {
                        if !g.done.isEmpty {
                            Text(g.done).foregroundStyle(.secondary)
                        } else if g.undo {
                            Button("Rückgängig") { Task { await Conversation.shared.undoMemory(message.id, g.id) } }
                        }
                        if let u = SparkAPI.wayLink("Ich → Gedächtnis") { Button("Ansehen") { openURL(u) } }
                    }
                }
                .padding(.vertical, 4).padding(.horizontal, 10)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.secondary.opacity(0.3), lineWidth: 1))
            }
        }
        .buttonStyle(.borderless)
        .font(.footnote)
        .padding(.leading, 6)
        .task { await Conversation.shared.memoryText(message.id) }
    }
}

/// "Ins Wissensbuch" under an answer that rests on at least two sources (wissensbuch.keep_offer)
struct WbFileButton: View {
    let message: Conversation.Message

    var body: some View {
        HStack {
            if message.filed == true {
                Label("Im Wissensbuch", systemImage: "checkmark").foregroundStyle(.secondary)
            } else {
                Button { Task { await Conversation.shared.file(message.id) } } label: {
                    Label("Ins Wissensbuch", systemImage: "books.vertical")
                }
            }
            Spacer()
        }
        .buttonStyle(.borderless)
        .font(.footnote)
        .padding(.leading, 6)
    }
}

struct RateBar: View {
    let message: Conversation.Message
    @State private var sheet = false

    var body: some View {
        HStack(spacing: 14) {
            Button { Task { await Conversation.shared.rate(message.id, good: true) } } label: {
                Text(verbatim: "👍").opacity(message.rated == false ? 0.4 : 1)
            }
            .accessibilityLabel("Gute Antwort")
            Button { sheet = true } label: {
                Text(verbatim: "👎").opacity(message.rated == true ? 0.4 : 1)
            }
            .accessibilityLabel("Schlechte Antwort")
            Spacer()
        }
        .buttonStyle(.borderless)
        .font(.footnote)
        .padding(.leading, 6)
        .sheet(isPresented: $sheet) { RateSheet(message: message) }
    }
}

struct RateSheet: View {
    let message: Conversation.Message
    @Environment(\.dismiss) private var dismiss
    @State private var reason = ""
    @State private var note = ""
    @State private var question = false
    @State private var soll = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Was war falsch?") {
                    Picker("Grund", selection: $reason) {
                        Text("ohne Grund").tag("")
                        ForEach(Conversation.rateReasons) { r in Text(r.label).tag(r.id) }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                    TextField("Kurz, freiwillig", text: $note)
                        .onChange(of: note) { if note.count > 200 { note = String(note.prefix(200)) } }
                    Toggle("Frage mitschicken (hilft beim Vorschlag)", isOn: $question)
                }
                Section("Hätte nachsehen sollen in (freiwillig)") {
                    Picker("Hätte nachsehen sollen in", selection: $soll) {
                        Text("weiß nicht").tag("")
                        ForEach(Conversation.rateSoll) { r in Text(r.label).tag(r.id) }
                    }
                    .pickerStyle(.menu)
                }
            }
            .navigationTitle("Schlechte Antwort")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Melden") {
                        Task { await Conversation.shared.rate(message.id, good: false, reason: reason, note: note, question: question, soll: soll) }
                        dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
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

/// A page under Einstellungen that is open while its right goes away (the admin blocks it, Funktionen): it stays open
/// with a note instead of vanishing under the finger; back closes it (plaene/ruhige-seiten.md)
private struct KeepOpen: ViewModifier {
    let key: String
    let on: Bool
    @Binding var open: Set<String>

    func body(content: Content) -> some View {
        content
            .onAppear { open.insert(key) }
            .safeAreaInset(edge: .top) {
                if !on {
                    Label("Gerade vom Admin ausgeschaltet. Zurück schließt die Seite.", systemImage: "lock")
                        .font(.footnote).padding(8).frame(maxWidth: .infinity).background(.thinMaterial)
                }
            }
    }
}

extension View {
    fileprivate func keepOpen(_ key: String, _ on: Bool, _ open: Binding<Set<String>>) -> some View {
        modifier(KeepOpen(key: key, on: on, open: open))
    }
}

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var talk: Conversation
    @AppStorage("handsFree") private var handsFree = false
    /// CarPlay: „Briefing beim Einsteigen“ (Prefs.carBriefing), only on this iPhone
    @AppStorage("carBriefing") private var carBriefing = false
    @AppStorage("bargeIn") private var bargeIn = true
    /// Antworten vorlesen: the profile's switch (speak), like Freihändig; "Auf diesem iPhone" only here (Prefs.speakHere)
    @AppStorage("speakAnswers") private var speakAnswers = true
    @AppStorage("speakHere") private var speakHere = true
    @AppStorage("wake") private var wake = false
    @AppStorage("wakeWord") private var wakeWord: WakeWord.Word = .spark
    @AppStorage("stand") private var stand = false
    @AppStorage("batteryMinutes") private var batteryMinutes = Prefs.batteryDefault
    @AppStorage("speakNotes") private var speakNotes = true
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = false
    /// Freihändig and Ins Wort fallen are the profile's own values (hands, barge), the same as in the browser:
    /// read once when the page opens, saved back on every change (plan „Vereinheitlichen“ Phase 6)
    @State private var synced = false
    /// Ich → Mein Zustand: only when /api/features says this profile may use it ("mystatus", can)
    @State private var myStatus = false
    /// Gesicht: the profile's own face ("" = the Spark's), the same value as Ich → Gespräch → Anzeige in the panel
    @State private var face = ""
    /// the pages open below this one: they keep their link while open, even when their right goes away meanwhile
    @State private var openPages: Set<String> = []

    var body: some View {
        NavigationStack {
            Form {
                Section("Gekoppelt") {
                    LabeledContent("Profil", value: app.profile)
                    LabeledContent("Spark", value: Store.baseURL?.host ?? "")
                }
                Section {
                    Picker("Gesicht", selection: $face) {
                        Text("Vorgabe des Spark").tag("")
                        Text("Roboter").tag("robot")
                        Text("Comic").tag("comic")
                        Text("Comic (Frau)").tag("comic_woman")
                    }
                } footer: {
                    Text(SparkAPI.way(String(localized: "Nur für dich, auf all deinen Geräten. Im Panel steht es unter Ich → Gespräch.")))
                }
                // saved for the profile, then hello again: the face on screen follows (own pick, else the Spark's)
                .onChange(of: face) { _, v in
                    if synced { Task { try? await SparkAPI.current?.saveProfileSettings(["face": v]); await talk.check() } }
                }
                Section {
                    NavigationLink("Mein Profil") { ProfileView() }
                    if ThingsView.any(talk.allowed) || openPages.contains("things") {
                        NavigationLink("Meine Sachen") { ThingsView().keepOpen("things", ThingsView.any(talk.allowed), $openPages) }
                    }
                    if talk.allowed.areas.contains("app_mine") || openPages.contains("mine") {
                        NavigationLink("Mein Alltag") { MineView().keepOpen("mine", talk.allowed.areas.contains("app_mine"), $openPages) }
                    }
                    if myStatus || openPages.contains("status") {
                        NavigationLink("Mein Zustand") { MyStatusView().keepOpen("status", myStatus, $openPages) }
                    }
                    if talk.allowed.areas.contains("app_auto") || openPages.contains("auto") {
                        NavigationLink("Von selbst") { AutoView().keepOpen("auto", talk.allowed.areas.contains("app_auto"), $openPages) }
                    }
                    if talk.allowed.areas.contains("app_voice") || openPages.contains("voice") {
                        NavigationLink("Stimme einlernen") { VoiceView().keepOpen("voice", talk.allowed.areas.contains("app_voice"), $openPages) }
                    }
                    if talk.allowed.areas.contains("app_accounts") || openPages.contains("accounts") {
                        NavigationLink("Konten verbinden") { AccountsView().keepOpen("accounts", talk.allowed.areas.contains("app_accounts"), $openPages) }
                    }
                    if talk.allowed.areas.contains("app_security") || openPages.contains("security") {
                        NavigationLink("Sicherheit") { SecurityView().keepOpen("security", talk.allowed.areas.contains("app_security"), $openPages) }
                    }
                    if !talk.allowed.adminRole.isEmpty {   // an admin profile: admin in its own app (V01.0.541)
                        NavigationLink("Spark verwalten") { AdminView() }
                    }
                    if talk.allowed.panel || openPages.contains("panel") {
                        NavigationLink("Im Panel öffnen") { PanelBridgeView(admin: !talk.allowed.adminRole.isEmpty).keepOpen("panel", talk.allowed.panel, $openPages) }
                    }
                } footer: {
                    Text("Stimme, Antworten und „Von selbst“ wie im Panel.")
                }
                NotausSection()
                if talk.allowed.report { ReportSection() }
                Section {
                    Button("Ton-Protokoll kopieren") {
                        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
                        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? ""
                        UIPasteboard.general.string = "Spark-App \(v) (\(b)) · Ton\n```\n" + AudioEngine.diary.joined(separator: "\n") + "\n```"
                    }
                } footer: {
                    Text("Bleibt eine Antwort stumm oder hakt CarPlay: hier tippen und in den Thread einfügen. Es steht nur drin, wann der Ton startet, wohin er geht und was CarPlay tut, nie was gesagt wurde.")
                }
                Section {
                    Toggle("Freihändig", isOn: $handsFree)
                    Toggle("Ins Wort fallen", isOn: $bargeIn)
                } header: { Text("Gespräch") } footer: {
                    Text("Freihändig: nach jeder Antwort hört die App wieder zu, bis 8 Sekunden lang nichts kommt. Ins Wort fallen: einfach losreden hält die Antwort an. Gilt für dein Profil, also auch im Browser.")
                }
                .onChange(of: handsFree) { _, v in if synced { Task { await saveTalk("hands", v) } } }
                .onChange(of: bargeIn) { _, v in if synced { Task { await saveTalk("barge", v) } } }
                Section {
                    Toggle("Briefing beim Einsteigen", isOn: $carBriefing)
                } header: { Text("CarPlay") } footer: {
                    Text("Einmal am Tag, wenn sich das iPhone mit dem Auto verbindet: Termine, Fristen und Wetter, gesprochen. Gilt nur für dieses iPhone. Im Auto fällt Spark dir nicht ins Wort; zum Unterbrechen „Mit Spark sprechen“ antippen.")
                }
                Section {
                    Toggle("Antworten vorlesen", isOn: $speakAnswers)
                    Toggle("Auf diesem iPhone vorlesen", isOn: $speakHere).disabled(!speakAnswers)
                } header: { Text("Sprachausgabe") } footer: {
                    Text("Aus: Antworten kommen nur als Text. Der erste Schalter gilt für dein Profil auf allen Geräten, der zweite nur hier. In CarPlay spricht die App immer.")
                }
                .onChange(of: speakAnswers) { _, v in if synced { Task { await saveTalk("speak", v) } } }
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
                        Text(SparkAPI.way(String(localized: "Im Panel unter Ich → iPhone-App „Dauerhaft zuhören erlauben“ einschalten.")))
                    }
                }
                Section {
                    Toggle("Von selbst sprechen", isOn: $speakNotes).disabled(!talk.allowed.proactive)
                } footer: {
                    if talk.allowed.proactive {
                        Text("Hinweise, die der Spark von selbst gibt (Morgenrunde, Erinnerungen), sagt die App laut, solange sie offen ist.")
                    } else {
                        Text(SparkAPI.way(String(localized: "Der Admin hat „Von selbst melden“ noch nicht freigegeben, oder du hast es unter Ich → Von selbst ausgeschaltet.")))
                    }
                }
                Section {
                    Text("„Hey Siri, Frag Spark“ fragt den Spark auch ohne die App zu öffnen, auch mit AirPods und im Auto.")
                    Text("Schnellstart: In den iPhone-Einstellungen unter Action-Button → Kurzbefehl „Spark zuhören“ wählen. Dasselbe gibt es im Kontrollzentrum und als Widget für den Sperrbildschirm.")
                        .foregroundStyle(.secondary)
                    Text(SparkAPI.way(String(localized: "Was die App darf, stellst du im Panel unter Ich → iPhone-App ein. Dort entfernst du das iPhone auch, wenn es verloren geht.")))
                        .foregroundStyle(.secondary)
                }
                if talk.allowed.updateNotify || talk.allowed.updateStart {
                    Section {
                        NavigationLink("Spark-Version") { UpdateView() }
                    } footer: {
                        Text("Neue geprüfte Versionen und das Update des Spark.")
                    }
                }
                Section {
                    Button("Entkoppeln", role: .destructive) { confirm = true }
                }
                Section {
                    LabeledContent("App", value: AppInfo.version)
                }
            }
            .navigationTitle("Einstellungen")
            .onAppear { openPages.removeAll() }   // back on this page: nothing below is open any more
            .task { await loadTalk() }
            .task {
                guard Demo.scene == nil else { return }
                myStatus = SparkAPI.can(Merken.object("funktionen")?.d, "mystatus")   // the last state first (Merken.swift)
                if let api = SparkAPI.current, let d = try? await api.object("GET", "api/features") {
                    Merken.keepObject("funktionen", d)
                    myStatus = SparkAPI.can(d, "mystatus")
                }
            }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
            .confirmationDialog("Schlüssel von diesem iPhone löschen?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Entkoppeln", role: .destructive) {
                    app.unpair()
                    dismiss()
                }
            } message: {
                Text(SparkAPI.way(String(localized: "Im Panel unter Ich → iPhone-App das iPhone auch entfernen, dann gilt der Schlüssel nirgends mehr.")))
            }
        }
    }

    private func loadTalk() async {
        guard Demo.scene == nil, let api = SparkAPI.current, let d = try? await api.profileSettings(),
              let p = d["settings"] as? [String: Any] else { synced = true; return }
        Merken.keepObject("einstellungen", d)
        if let h = p["hands"] as? Bool, h != handsFree { handsFree = h }
        if let b = p["barge"] as? Bool, b != bargeIn { bargeIn = b }
        if let v = p["speak"] as? Bool, v != speakAnswers { speakAnswers = v }
        if let f = p["face"] as? String, ["", "robot", "comic", "comic_woman"].contains(f), f != face { face = f }
        // the onChange calls for the values just read run before this (at worst they save the same value back)
        await Task.yield()
        synced = true
    }

    private func saveTalk(_ key: String, _ value: Bool) async {
        try? await SparkAPI.current?.saveProfileSettings([key: value])
    }
}
