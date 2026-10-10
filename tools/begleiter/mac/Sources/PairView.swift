import AppKit
import SwiftUI

/// Pairing: the setup line from the panel (Ich → Begleiter → „Gerät koppeln“), or address and code separately.
@MainActor
final class PairController: ObservableObject {
    static let shared = PairController()
    static let windowID = "pair"

    @Published var line = ""
    @Published var base = ""
    @Published var code = ""
    @Published var separate = false
    @Published private(set) var busy = false
    @Published var status = ""
    @Published var isError = false

    func pair() {
        guard !busy else { return }
        let checked: (base: String, code: String)
        do {
            checked = try separate ? SparkAddress.check(base: base, code: code) : SparkAddress.parse(line: line)
        } catch let f as SparkAddress.Failure {
            show(f.message, error: true)
            return
        } catch {
            show("Das hat nicht geklappt.", error: true)
            return
        }
        busy = true
        show("Kopple …", error: false)
        let name = SparkAddress.deviceName(Host.current().localizedName)
        Task { @MainActor [weak self] in
            let client = SparkClient(base: checked.base, key: nil)
            defer { client.close() }
            do {
                let r = try await client.pair(code: checked.code, name: name)
                guard Keychain.save(base: checked.base, key: r.key) else {
                    self?.busy = false
                    self?.show("Der Schlüssel konnte nicht im Schlüsselbund gespeichert werden.", error: true)
                    return
                }
                AppModel.shared.connect(base: checked.base, key: r.key)
                self?.busy = false
                self?.line = ""
                self?.code = ""
                self?.show("", error: false)
                Windows.shared.close(Self.windowID)
                HUD.show(r.profile.isEmpty ? "Gekoppelt." : "Gekoppelt mit dem Profil \(DeskConfig.plain(r.profile, max: 80)).",
                         symbol: "checkmark.circle")
            } catch {
                self?.busy = false
                let msg: String
                if let p = error as? SparkProblem {
                    msg = p.message
                } else {
                    msg = "Das Koppeln hat nicht geklappt."
                }
                self?.show("Koppeln hat nicht geklappt: \(msg)", error: true)
            }
        }
    }

    func show(_ s: String, error: Bool) {
        status = s
        isError = error
    }
}

extension Windows {
    static func showPairing(message: String = "") {
        let c = PairController.shared
        if !message.isEmpty { c.show(message, error: true) }
        Windows.shared.show(PairController.windowID, title: "Spark-Begleiter koppeln", size: NSSize(width: 520, height: 330)) {
            PairView(c: c)
        }
    }
}

struct PairView: View {
    @ObservedObject var c: PairController

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(verbatim: "Mit dem eigenen Spark koppeln")
                .font(.headline)
            Text(verbatim: "Im Panel unter Ich → Begleiter → „Gerät koppeln“ eine Einrichtungszeile holen und hier einfügen. Sie gilt 10 Minuten und nur einmal.")
                .fixedSize(horizontal: false, vertical: true)
                .foregroundColor(.secondary)

            if c.separate {
                TextField("Adresse, z. B. https://spark.example.de", text: $c.base)
                    .textFieldStyle(.roundedBorder)
                TextField("Code, z. B. ABCD-EFGH", text: $c.code)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { c.pair() }
            } else {
                TextField("https://spark.example.de#begleiter=ABCD-EFGH", text: $c.line)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { c.pair() }
            }
            Toggle("Adresse und Code einzeln eingeben", isOn: $c.separate)

            Text(verbatim: "Unverschlüsselt (http) geht nur im Heimnetz; sonst die https-Adresse des Spark.")
                .font(.caption)
                .foregroundColor(.secondary)

            if !c.status.isEmpty {
                Text(verbatim: c.status)
                    .foregroundColor(c.isError ? .red : .secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 0)
            HStack {
                if c.busy { ProgressView().controlSize(.small) }
                Spacer()
                Button("Abbrechen") { Windows.shared.close(PairController.windowID) }
                    .keyboardShortcut(.cancelAction)
                Button("Koppeln") { c.pair() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(c.busy)
            }
        }
        .padding(16)
        .frame(minWidth: 460, minHeight: 300)
    }
}
