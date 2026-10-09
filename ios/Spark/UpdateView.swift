import LocalAuthentication
import SwiftUI

/// "Spark-Version": the installed and the newest tested version with its changes, and, when the admin
/// allowed it for this profile, starting the update (Face ID, then a fresh code from the authenticator app).
/// The Spark decides everything else: only versions with green tests, one start per 10 minutes.
@MainActor
final class UpdateModel: ObservableObject {
    @Published var state = UpdateState()
    @Published var loading = true
    @Published var error: String?
    /// the update was started here: follow it until the Spark is back
    @Published var following = false
    @Published var restarting = false
    @Published var finished: String?
    private var poll: Task<Void, Never>?
    /// the old update's "done" stays on the Spark until the new one writes its first step
    private var sawRunning = false

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            state = try await api.updateState()
            error = nil
            restarting = false
            if state.running { sawRunning = true }
            if state.running { follow() }
        } catch {
            if following { restarting = true; sawRunning = true } else { self.error = error.localizedDescription }
        }
        loading = false
    }

    /// Face ID (or the iPhone code) first, so the code alone in someone's hand is not enough.
    func unlock() async -> Bool {
        let ctx = LAContext()
        var err: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) else {
            error = String(localized: "Auf diesem iPhone ist keine Code-Sperre eingerichtet.")
            return false
        }
        do {
            return try await ctx.evaluatePolicy(.deviceOwnerAuthentication,
                                                localizedReason: String(localized: "Spark-Update starten"))
        } catch {
            return false
        }
    }

    func start(code: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            let version = try await api.startUpdate(code: code)
            error = nil
            finished = nil
            following = true
            sawRunning = false
            state.running = true
            state.step = String(localized: "Update auf \(version) gestartet …")
            follow()
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Asks every few seconds while the update runs; while the Spark restarts it does not answer.
    private func follow() {
        following = true
        guard poll == nil else { return }
        poll = Task { [weak self] in
            let until = Date().addingTimeInterval(45 * 60)
            while !Task.isCancelled, Date() < until {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                guard let self else { return }
                await self.load()
                if self.sawRunning && !self.state.running && !self.restarting && self.state.done {
                    self.finished = self.state.ok == true
                        ? String(localized: "Fertig. Der Spark läuft wieder mit \(self.state.installed).")
                        : String(localized: "Das Update hat nicht geklappt. Der Spark läuft weiter mit der alten Version; Details im Panel unter Zustand → System/Update.")
                    self.following = false
                    break
                }
            }
            self?.poll = nil
        }
    }

    func stop() {
        poll?.cancel()
        poll = nil
    }
}

struct UpdateView: View {
    @StateObject private var m = UpdateModel()
    @State private var asking = false
    @State private var code = ""

    var body: some View {
        Form {
            if m.loading {
                ProgressView()
            } else {
                if let e = m.error {
                    Section { Text(verbatim: e).foregroundStyle(.red) }
                }
                Section {
                    LabeledContent("Installiert") { Text(verbatim: m.state.installed) }
                    if let latest = m.state.latest, m.state.newer {
                        LabeledContent("Neu und geprüft") { Text(verbatim: latest).bold() }
                    } else if let e = m.state.error {
                        Text(verbatim: e).font(.footnote).foregroundStyle(.secondary)
                    } else if !m.state.running && !m.following {
                        Label("Der Spark ist aktuell.", systemImage: "checkmark.circle").foregroundStyle(.green)
                    }
                }
                if m.state.running || m.following {
                    Section {
                        ProgressView(value: Double(min(max(m.state.percent, 0), 100)), total: 100)
                        Text(verbatim: m.restarting ? String(localized: "Spark startet neu …") : m.state.step)
                            .font(.footnote).foregroundStyle(.secondary)
                    } header: { Text("Update läuft") } footer: {
                        Text("Der Assistent ist währenddessen kurz nicht erreichbar.")
                    }
                }
                if let f = m.finished {
                    Section { Text(verbatim: f) }
                }
                if m.state.newer && !m.state.changes.isEmpty {
                    Section {
                        ForEach(Array(m.state.changes.enumerated()), id: \.offset) { _, c in
                            Text(verbatim: c).font(.footnote)
                        }
                    } header: { Text("Was sich ändert") }
                }
                if m.state.start && m.state.newer && !m.state.running && !m.following {
                    Section {
                        Button("Jetzt aktualisieren") {
                            Task { if await m.unlock() { code = ""; asking = true } }
                        }
                        .disabled(m.state.wait > 0)
                    } footer: {
                        if m.state.wait > 0 {
                            Text("Gerade erst gestartet. Wieder möglich in \(max(1, m.state.wait / 60)) Minuten.")
                        } else {
                            Text("Erst eine Sicherung, dann die neue Version. Du bestätigst mit Face ID und dem Code aus deiner Authenticator-App.")
                        }
                    }
                }
            }
        }
        .navigationTitle("Spark-Version")
        .refreshable { await m.load() }
        .task { await m.load() }
        .onDisappear { m.stop() }
        .alert("Code aus der Authenticator-App", isPresented: $asking) {
            TextField("123456", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
            Button("Update starten") {
                let c = code.filter(\.isNumber)
                Task { await m.start(code: String(c.prefix(6))) }
            }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Der Code gilt nur einmal.")
        }
    }
}
