import CarPlay
import Combine
import SwiftUI
import UIKit

/// CarPlay: an own icon in the car. Tapping "Mit Spark sprechen" starts a hands-free conversation
/// (the same assistant as on the phone, with short answers); the car screen shows only the state
/// (listening, thinking, speaking) with the profile's face (robot or comic, from hello and redrawn when it arrives later, as a still picture:
/// CarPlay allows no own drawing or animation), never text. Needs the CarPlay entitlement for voice-based
/// conversational apps (Spark.entitlements; granted by Apple since V01.0.676, docs/de/iphone-app.md).
@MainActor
final class CarPlayScene: UIResponder, CPTemplateApplicationSceneDelegate {
    private var interface: CPInterfaceController?
    private var voice: CPVoiceControlTemplate?
    private var shown = false
    private var watch: AnyCancellable?
    private var watchFace: AnyCancellable?
    private var start: CPListItem?
    private var fresh: CPListItem?
    private var list: CPListTemplate?
    private var watchAreas: AnyCancellable?
    /// the face the pictures show; the profile's choice arrives with hello, often only after CarPlay connected
    private var face = ""
    private var faceLater = false

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didConnect interfaceController: CPInterfaceController) {
        interface = interfaceController
        let talk = Conversation.shared
        talk.inCar = true
        let start = CPListItem(text: String(localized: "Mit Spark sprechen"), detailText: String(localized: "Antippen und losreden"),
                               image: nil)
        start.handler = { [weak self] _, done in
            self?.begin(fresh: false)
            done()
        }
        self.start = start
        let fresh = CPListItem(text: String(localized: "Neues Gespräch"), detailText: String(localized: "Das bisherige Gespräch vergessen"),
                               image: UIImage(systemName: "square.and.pencil"))
        fresh.handler = { [weak self] _, done in
            self?.begin(fresh: true)
            done()
        }
        self.fresh = fresh
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
        if shown { faceLater = true; return }
        face = kind
        faceLater = false
        voice = CPVoiceControlTemplate(voiceControlStates: [
            CPVoiceControlState(identifier: "listen", titleVariants: [String(localized: "Ich höre zu …")],
                                image: FaceStill.image(kind, .listen) ?? UIImage(systemName: "mic.fill"), repeats: true),
            CPVoiceControlState(identifier: "think", titleVariants: [String(localized: "Denke nach …")],
                                image: FaceStill.image(kind, .think) ?? UIImage(systemName: "ellipsis"), repeats: true),
            CPVoiceControlState(identifier: "speak", titleVariants: [String(localized: "Spark spricht …")],
                                image: FaceStill.image(kind, .speak) ?? UIImage(systemName: "speaker.wave.2.fill"), repeats: true)])
    }

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didDisconnectInterfaceController interfaceController: CPInterfaceController) {
        watch = nil
        watchFace = nil
        watchAreas = nil
        list = nil
        fresh = nil
        interface = nil
        start = nil
        voice = nil
        face = ""
        shown = false
        let talk = Conversation.shared
        talk.inCar = false
        talk.stop()
    }

    /// The rows: talking, a new conversation, and with Kalender and E-Mail released the assistant reads them aloud
    /// (plan kalender-mail Stufe 4: the car shows no text, the answer is spoken like any other).
    private func items(_ areas: Set<String>) -> [CPListItem] {
        var out = [start, fresh].compactMap { $0 }
        if areas.contains("calendar") {
            let cal = CPListItem(text: String(localized: "Termine vorlesen"), detailText: String(localized: "Was heute und morgen ansteht"),
                                 image: UIImage(systemName: "calendar"))
            cal.handler = { _, done in
                Conversation.shared.write(String(localized: "Was steht heute und morgen an?"))
                done()
            }
            out.append(cal)
        }
        if areas.contains("mail") {
            let post = CPListItem(text: String(localized: "Neue Mails vorlesen"), detailText: String(localized: "Wer geschrieben hat und worum es geht"),
                                  image: UIImage(systemName: "envelope"))
            post.handler = { _, done in
                Conversation.shared.write(String(localized: "Habe ich neue Mails?"))
                done()
            }
            out.append(post)
        }
        return out
    }

    private func begin(fresh: Bool) {
        let talk = Conversation.shared
        if fresh { talk.restart() }
        if talk.phase == .idle || talk.phase == .waiting { talk.tap() }
    }

    private func show(_ phase: Conversation.Phase) {
        guard let interface, let voice else { return }
        let state: String?
        switch phase {
        case .listening: state = "listen"
        case .transcribing, .thinking: state = "think"
        case .speaking: state = "speak"
        case .idle, .waiting: state = nil
        }
        if let state {
            if !shown {
                shown = true
                interface.presentTemplate(voice, animated: true, completion: nil)
            }
            voice.activateVoiceControlState(withIdentifier: state)
        } else if shown {
            shown = false
            interface.dismissTemplate(animated: true, completion: nil)
            if faceLater { use(face: Conversation.shared.allowed.face) }
        }
    }
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
