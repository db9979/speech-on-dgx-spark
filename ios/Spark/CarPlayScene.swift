import CarPlay
import Combine
import SwiftUI
import UIKit

/// CarPlay: an own icon in the car. Tapping "Mit Spark sprechen" starts a hands-free conversation
/// (the same assistant as on the phone, with short answers); the car screen shows only the state
/// (listening, thinking, speaking) with the profile's face (robot or comic, from hello and redrawn when it arrives later, as a still picture:
/// CarPlay allows no own drawing or animation), never text. Needs the CarPlay entitlement for voice-based
/// conversational apps (Spark.entitlements; granted by Apple since V01.0.676, docs/de/iphone-app.md).
/// CarPlay stabil (V01.0.871): the voice template is shown and hidden one step at a time (CarPlay refuses a second
/// present or dismiss while one runs, the template then stayed away while Spark spoke, and a tapped row seemed to do
/// nothing), a row always starts something or shows why not, and every step goes into the Ton-Protokoll.
@MainActor
final class CarPlayScene: UIResponder, CPTemplateApplicationSceneDelegate {
    private var interface: CPInterfaceController?
    private var voice: CPVoiceControlTemplate?
    /// the state the voice template should show, nil for the list
    private var want: String?
    /// a present or dismiss is under way: the next one waits for its completion (sync)
    private var moving = false
    private var refused = 0
    /// back to the list only after a short moment: the step between two answers does not flicker
    private var hide: Task<Void, Never>?
    private var watch: AnyCancellable?
    private var watchFace: AnyCancellable?
    private var start: CPListItem?
    private var fresh: CPListItem?
    private var repeatRow: CPListItem?
    private var list: CPListTemplate?
    private var watchAreas: AnyCancellable?
    /// the face the pictures show; the profile's choice arrives with hello, often only after CarPlay connected
    private var face = ""
    private var faceLater = false

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didConnect interfaceController: CPInterfaceController) {
        interface = interfaceController
        AudioEngine.note("CarPlay: verbunden")
        let talk = Conversation.shared
        talk.inCar = true
        if talk.phase == .waiting { talk.stop() }   // no wake word in the car („2a“): base() closes the microphone
        let start = CPListItem(text: String(localized: "Mit Spark sprechen"), detailText: String(localized: "Antippen und losreden"),
                               image: nil)
        start.handler = { [weak self] _, done in
            done()
            self?.begin(fresh: false)
        }
        self.start = start
        let fresh = CPListItem(text: String(localized: "Neues Gespräch"), detailText: String(localized: "Das bisherige Gespräch vergessen"),
                               image: UIImage(systemName: "square.and.pencil"))
        fresh.handler = { [weak self] _, done in
            done()
            self?.begin(fresh: true)
        }
        self.fresh = fresh
        let again = CPListItem(text: String(localized: "Letzte Antwort wiederholen"), detailText: String(localized: "Spark sagt sie noch einmal"),
                               image: UIImage(systemName: "arrow.counterclockwise"))
        again.handler = { [weak self] _, done in
            done()
            self?.again()
        }
        self.repeatRow = again
        let list = CPListTemplate(title: "Spark", sections: [CPListSection(items: items(talk.allowed.areas))])
        self.list = list
        interfaceController.setRootTemplate(list, animated: false, completion: nil)
        // hello often arrives after the car connected: the rows for Kalender and E-Mail follow it
        watchAreas = talk.$allowed.map(\.areas).removeDuplicates().receive(on: RunLoop.main).sink { [weak self] a in
            guard let self, let list = self.list else { return }
            list.updateSections([CPListSection(items: self.items(a))])
        }
        watchFace = talk.$allowed.map(\.face).removeDuplicates().receive(on: RunLoop.main).sink { [weak self] f in self?.use(face: f) }
        watch = talk.$phase.receive(on: RunLoop.main).sink { [weak self] p in self?.show(p) }
        // started by the car alone, the phone screen never appeared and nothing asked the Spark yet (hello):
        // without it the car would keep the defaults (robot face, no profile switches)
        Task { await talk.check() }
    }

    /// Draws the pictures for the profile's face. A voice template on screen keeps its pictures (CarPlay
    /// cannot change them while shown), so a change then waits until it is dismissed.
    private func use(face kind: String) {
        guard kind != face else { return }
        start?.setImage(FaceStill.image(kind, .idle) ?? UIImage(systemName: "waveform"))
        if moving || (voice != nil && interface?.presentedTemplate === voice) { faceLater = true; return }
        face = kind
        faceLater = false
        voice = CPVoiceControlTemplate(voiceControlStates: [
            CPVoiceControlState(identifier: "listen", titleVariants: [String(localized: "Ich höre zu …")],
                                image: FaceStill.image(kind, .listen) ?? UIImage(systemName: "mic.fill"), repeats: true),
            CPVoiceControlState(identifier: "think", titleVariants: [String(localized: "Denke nach …")],
                                image: FaceStill.image(kind, .think) ?? UIImage(systemName: "ellipsis"), repeats: true),
            CPVoiceControlState(identifier: "speak", titleVariants: [String(localized: "Spark spricht …")],
                                image: FaceStill.image(kind, .speak) ?? UIImage(systemName: "speaker.wave.2.fill"), repeats: true),
            // a short moment before the list comes back, so the car says why nothing happens instead of just closing
            CPVoiceControlState(identifier: "offline", titleVariants: [String(localized: "Spark nicht erreichbar")],
                                image: FaceStill.image(kind, .sad) ?? UIImage(systemName: "wifi.slash"), repeats: false),
            CPVoiceControlState(identifier: "fail", titleVariants: [String(localized: "Hat nicht geklappt")],
                                image: FaceStill.image(kind, .sad) ?? UIImage(systemName: "exclamationmark.triangle"), repeats: false),
            CPVoiceControlState(identifier: "none", titleVariants: [String(localized: "Noch keine Antwort")],
                                image: FaceStill.image(kind, .idle) ?? UIImage(systemName: "text.bubble"), repeats: false)])
    }

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didDisconnectInterfaceController interfaceController: CPInterfaceController) {
        AudioEngine.note("CarPlay: getrennt")
        hide?.cancel()
        hide = nil
        want = nil
        moving = false
        watch = nil
        watchFace = nil
        watchAreas = nil
        list = nil
        fresh = nil
        repeatRow = nil
        interface = nil
        start = nil
        voice = nil
        face = ""
        let talk = Conversation.shared
        talk.inCar = false
        talk.stop()
    }

    /// The rows: talking, a new conversation, and with Kalender and E-Mail released the assistant reads them aloud
    /// (plan kalender-mail Stufe 4: the car shows no text, the answer is spoken like any other).
    private func items(_ areas: Set<String>) -> [CPListItem] {
        var out = [start, repeatRow, fresh].compactMap { $0 }
        if areas.contains("calendar") {
            let cal = CPListItem(text: String(localized: "Termine vorlesen"), detailText: String(localized: "Was heute und morgen ansteht"),
                                 image: UIImage(systemName: "calendar"))
            cal.handler = { [weak self] _, done in
                done()
                self?.ask(String(localized: "Was steht heute und morgen an?"), "Termine")
            }
            out.append(cal)
        }
        if areas.contains("mail") {
            let post = CPListItem(text: String(localized: "Neue Mails vorlesen"), detailText: String(localized: "Wer geschrieben hat und worum es geht"),
                                  image: UIImage(systemName: "envelope"))
            post.handler = { [weak self] _, done in
                done()
                self?.ask(String(localized: "Habe ich neue Mails?"), "Mails")
            }
            out.append(post)
        }
        if areas.contains("fuerdich") {   // Für dich (fuerdich.py): deadlines and open bills, read aloud like any answer
            let due = CPListItem(text: String(localized: "Fristen vorlesen"), detailText: String(localized: "Was du diese Woche erledigen musst"),
                                 image: UIImage(systemName: "tray.full"))
            due.handler = { [weak self] _, done in
                done()
                self?.ask(String(localized: "Was muss ich diese Woche erledigen?"), "Fristen")
            }
            out.append(due)
        }
        return out
    }

    /// "Mit Spark sprechen", "Neues Gespräch": always listens, also while Spark still speaks or thinks (before: a tap
    /// then did nothing and the row seemed stuck). Without the Spark the car says so instead of staying silent.
    private func begin(fresh: Bool) {
        let talk = Conversation.shared
        AudioEngine.note(fresh ? "CarPlay: Knopf Neues Gespräch" : "CarPlay: Knopf Sprechen")
        if fresh { talk.restart() }
        reachable { [weak self] in
            switch talk.phase {
            case .listening: self?.show(talk.phase)
            case .idle, .waiting: talk.tap()
            default:
                talk.stop()
                talk.tap()
            }
        }
    }

    /// „Letzte Antwort wiederholen“: the newest answer once more; with none yet the car says so for a moment.
    private func again() {
        AudioEngine.note("CarPlay: Knopf Wiederholen")
        reachable { [weak self] in
            if !Conversation.shared.repeatLast() { self?.flash("none") }
        }
    }

    /// A row that asks a fixed question (Termine, Mails, Fristen); `kind` is a fixed word for the Ton-Protokoll.
    private func ask(_ question: String, _ kind: String) {
        AudioEngine.note("CarPlay: Knopf \(kind)")
        reachable { Conversation.shared.write(question) }
    }

    /// Runs `go` when the Spark answers. A question in the car never waits in the outbox (its answer would start
    /// speaking by itself much later): without the Spark the car shows „Spark nicht erreichbar“ for a moment.
    private func reachable(_ go: @escaping @MainActor () -> Void) {
        let talk = Conversation.shared
        guard talk.unreachable else { go(); return }
        Task { [weak self] in
            if await talk.check() { go() } else { self?.flash("offline") }
        }
    }

    /// A state of trouble on the voice template for 3 s, then the list.
    private func flash(_ state: String) {
        AudioEngine.note("CarPlay: zeigt \(state)")
        want = state
        sync()
        later(3)
    }

    private func later(_ seconds: Double) {
        hide?.cancel()
        hide = Task { [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            guard let self, !Task.isCancelled else { return }
            self.want = nil
            self.sync()
        }
    }

    private func show(_ phase: Conversation.Phase) {
        let state: String?
        switch phase {
        case .listening: state = "listen"
        case .transcribing, .thinking: state = "think"
        case .speaking: state = "speak"
        case .idle, .waiting: state = nil
        }
        if let state {
            hide?.cancel()
            hide = nil
            want = state
            sync()
            return
        }
        guard want != nil, hide == nil else { return }
        // the conversation ended with an error: the car says why for a moment instead of just closing
        let talk = Conversation.shared
        if talk.unreachable { flash("offline") } else if talk.error != nil { flash("fail") } else { later(0.8) }
    }

    /// Brings the car to the wanted state, one present or dismiss at a time (CarPlay refuses a second one while one runs).
    /// Whether the template is up is asked from CarPlay itself (presentedTemplate), never kept in an own flag that could
    /// go wrong when the car closed it.
    private func sync() {
        guard let interface, let voice, !moving else { return }
        let up = interface.presentedTemplate === voice
        if let want {
            voice.activateVoiceControlState(withIdentifier: want)
            guard !up else { return }
            moving = true
            interface.presentTemplate(voice, animated: true) { [weak self] ok, _ in
                Task { @MainActor in self?.moved(ok, "auf") }
            }
        } else if up {
            moving = true
            interface.dismissTemplate(animated: true) { [weak self] ok, _ in
                Task { @MainActor in self?.moved(ok, "zu") }
            }
        } else if faceLater {
            use(face: Conversation.shared.allowed.face)
        }
    }

    private func moved(_ ok: Bool, _ how: String) {
        moving = false
        AudioEngine.note(ok ? "CarPlay: Sprachfenster \(how)" : "CarPlay: Sprachfenster \(how) abgelehnt")
        if ok {
            refused = 0
            sync()
        } else if refused < 3 {
            refused += 1
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in MainActor.assumeIsolated { self?.sync() } }
        }
    }

    // ---------------------------------------------------------------- the car screen in front or not (Ton-Protokoll)
    func sceneWillEnterForeground(_ scene: UIScene) { AudioEngine.note("CarPlay: vorn") }
    func sceneDidEnterBackground(_ scene: UIScene) { AudioEngine.note("CarPlay: Hintergrund") }
}

/// The picked face (FaceView's looks) as one still picture per state for CarPlay. The comic faces keep
/// their own life between frames, so a few frames are drawn invisibly first until the pose has settled
/// (before the first blink).
@MainActor
enum FaceStill {
    static func image(_ kind: String, _ mood: FaceMood, side: CGFloat = 240) -> UIImage? {
        let style: FaceStyle
        switch kind {
        case "comic": style = ComicFace()
        case "comic_woman": style = ComicFace(woman: true)
        default: style = RobotFace()
        }
        let t: (open: Double, smile: Double, eyeH: Double, halo: Double, brow: Double, look: Double)
        switch mood {
        case .listen: t = (0, 0.5, 28, 0.6, 0.8, 0)
        case .think: t = (1.5, 0, 20, 0.3, -0.4, 6)
        case .speak: t = (9, 0.7, 24, 0.55, 0.6, 0)
        default: t = (0, 1, 24, 0.22, 0, 0)
        }
        func pose(_ now: Double) -> FacePose {
            FacePose(mood: mood, now: now, mic: mood == .listen ? 0.5 : 0, out: mood == .speak ? 0.6 : 0, open: t.open,
                     smile: t.smile, eyeH: t.eyeH, lid: 1, brow: t.brow, halo: t.halo, cheeks: 0.5,
                     lookX: t.look, lookY: -t.look, bob: 0)
        }
        let drawing = Canvas { ctx, size in
            let s = min(size.width, size.height) / 200
            ctx.scaleBy(x: s, y: s)
            var warm = ctx
            warm.opacity = 0
            for i in 0..<28 { style.draw(&warm, pose(1 + Double(i) * 0.05)) }
            style.draw(&ctx, pose(2.4))
        }
        .frame(width: side, height: side)
        let r = ImageRenderer(content: drawing)
        r.scale = 2
        return r.uiImage
    }
}
