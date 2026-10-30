import AVFoundation
import AppKit
import SwiftUI

/// Part "speak" (Vorlesen): ⌥⌘L copies the marked text (like the writing help), the Spark reads it in the profile's
/// own voice (POST /api/desk/speak -> WAV), the Mac plays it. The same hotkey again (or "Stopp" on the pill) stops.
/// From the tray panel the clipboard is read aloud. The voice stays in memory only.
@MainActor
final class Speaker: ObservableObject {
    static let shared = Speaker()

    @Published private(set) var loading = false
    @Published private(set) var playing = false

    private var player: AVAudioPlayer?
    private var job: Task<Void, Never>?
    private var ticker: Task<Void, Never>?

    var active: Bool { loading || playing }

    /// the hotkey: stop when something runs, else read the marked text
    func toggle() {
        if active {
            stop()
            return
        }
        Task { await self.startFromSelection() }
    }

    private func checks() -> SparkClient? {
        let model = AppModel.shared
        guard let client = model.client else {
            Windows.showPairing()
            return nil
        }
        guard model.part("speak") else {
            HUD.show(AppModel.offHint("Vorlesen"))
            return nil
        }
        return client
    }

    private func startFromSelection() async {
        guard checks() != nil else { return }
        guard Access.trusted else {
            Access.askOnce()
            HUD.show("Zum Vorlesen von markiertem Text braucht der Begleiter die Freigabe Bedienungshilfen. Ohne: Text kopieren und im Menü „Zwischenablage vorlesen“ wählen.",
                     symbol: "hand.raised", seconds: 7)
            return
        }
        let text = await Clip.copySelection() ?? ""
        read(text)
    }

    /// the tray panel: the clipboard's text
    func readClipboard() {
        if active { stop() }
        read(NSPasteboard.general.string(forType: .string) ?? "")
    }

    func read(_ raw: String) {
        guard let client = checks() else { return }
        guard let p = SpeakText.prepare(raw) else {
            HUD.show("Erst Text markieren, dann \(AppModel.shared.hotkeyLabel(.speak).isEmpty ? "Vorlesen" : AppModel.shared.hotkeyLabel(.speak)).",
                     symbol: "speaker.wave.2")
            return
        }
        stop()
        loading = true
        SpeakPill.show(self)
        job = Task { @MainActor [weak self] in
            do {
                let wav = try await client.speak(p.text)
                guard let self, !Task.isCancelled, self.loading else { return }
                guard SpeakText.looksLikeWav(wav) else {
                    self.finish()
                    HUD.show("Der Spark hat keine Sprachausgabe geschickt.", symbol: "exclamationmark.triangle")
                    return
                }
                self.play(wav, cut: p.cut)
            } catch is CancellationError {
                self?.finish()
            } catch {
                self?.finish()
                HUD.show(AppModel.shared.absorb(error), symbol: "exclamationmark.triangle")
            }
        }
    }

    private func play(_ wav: Data, cut: Bool) {
        loading = false
        do {
            let p = try AVAudioPlayer(data: wav)
            p.prepareToPlay()
            guard p.play() else { throw RecorderError.noInput }
            player = p
            playing = true
            SpeakPill.show(self)
            if cut { HUD.show("Nur die ersten \(SpeakText.max) Zeichen werden vorgelesen.", symbol: "speaker.wave.2") }
            ticker?.cancel()
            ticker = Task { @MainActor [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    guard let self, let pl = self.player else { return }
                    if !pl.isPlaying {
                        self.finish()
                        return
                    }
                }
            }
        } catch {
            finish()
            HUD.show("Die Sprachausgabe lässt sich nicht abspielen.", symbol: "speaker.slash")
        }
    }

    func stop() {
        job?.cancel()
        job = nil
        player?.stop()
        finish()
    }

    private func finish() {
        ticker?.cancel()
        ticker = nil
        player = nil
        loading = false
        playing = false
        SpeakPill.hide()
    }

    /// part off: nothing keeps talking
    func apply(on: Bool) {
        if !on && active { stop() }
    }
}

/// "Spark liest vor" with Stopp: a small dark pill at the top of the screen (design A, like the recording pill).
struct SpeakPillView: View {
    @ObservedObject var speaker: Speaker
    let hotkey: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: speaker.loading ? "hourglass" : "speaker.wave.2.fill")
                .foregroundColor(Theme.accent)
            Text(verbatim: speaker.loading ? "Spark bereitet das Vorlesen vor …" : "Spark liest vor")
                .font(.system(size: 13, weight: .semibold))
            if !hotkey.isEmpty {
                KeyChip(text: hotkey, dark: true)
                    .help(Text(verbatim: "\(hotkey) hält an"))
            }
            Button("Stopp") { speaker.stop() }
                .buttonStyle(PillButtonStyle(primary: true))
        }
        .foregroundColor(Theme.pillFg)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Capsule().fill(Theme.visor))
        .overlay(Capsule().stroke(Theme.onAccent.opacity(0.08), lineWidth: 1))
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(verbatim: "Spark liest vor"))
    }
}

@MainActor
enum SpeakPill {
    private static var panel: NSPanel?

    static func show(_ s: Speaker) {
        let p = panel ?? FloatingPanel.make()
        panel = p
        FloatingPanel.show(p, SpeakPillView(speaker: s, hotkey: AppModel.shared.hotkeyLabel(.speak)))
        // below the HUD's place, so both can be seen
        p.setFrameOrigin(NSPoint(x: p.frame.origin.x, y: p.frame.origin.y - 64))
    }

    static func hide() {
        panel?.orderOut(nil)
    }
}
